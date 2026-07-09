"""Hidden reference tracer.

DeltaV can't tell you that a control module is used by a phase when the phase
reaches it through a *unit alias* — the phase only knows the alias name, and the
alias->module binding lives on the unit/instance, so the module's own
cross-reference comes up empty. Same blind spot for EM member resolutions and
parameter-level references buried in FBD/SFC expressions.

This tracer walks all the indirection layers and answers: "where is this module
(or parameter) actually referenced, and through what path?"

Reference layers resolved:
  1. Direct  — the tag appears literally (module instance, MODULE=, TAG lists).
  2. Alias   — an ALIAS_DEFINITION binds NAME->module (VALUE="tag"); phases/recipes
               reference ^/ALIAS/... in SFC action/transition expressions. We report
               the alias AND every phase step/transition/expression that uses it.
  3. EM block resolution — MODULE_BLOCK_RESOLUTION NAME=member { MODULE=tag } inside a
               deployed EM instance; the EM's logic references ^/member/...
  4. Parameter — when a specific parameter is asked for (e.g. TAG/PV.CV), we keep only
               references whose expression touches that parameter.

Output is a list of findings, each with a human-readable resolution path so you can
see exactly how the link was made. Nothing here touches core/.
"""

import re


# ── binding maps ─────────────────────────────────────────────────────────────
def _alias_bindings(text):
    """alias name -> {tag, unit} from ALIAS_RESOLUTION blocks (the unit-level binding
    of a phase alias to a real module tag). This is the binding DeltaV hides: the phase
    references the alias name, and the alias->tag link lives on the unit instance."""
    out = {}
    # index unit instances so we can attribute a resolution to its owning unit
    units = []
    for m in re.finditer(r'UNIT_MODULE(?:_INSTANCE)?\s+TAG="([^"]+)"|'
                         r'MODULE_INSTANCE TAG="([^"]+)"[^\n]*UNIT', text):
        units.append((m.start(), m.group(1) or m.group(2)))
    units.sort()

    def unit_at(pos):
        lo, hi, ans = 0, len(units) - 1, ''
        while lo <= hi:
            mid = (lo + hi) // 2
            if units[mid][0] <= pos:
                ans = units[mid][1]; lo = mid + 1
            else:
                hi = mid - 1
        return ans

    for m in re.finditer(
            r'ALIAS_RESOLUTION NAME="([A-Za-z0-9_\-]+)"\s*\{\s*VALUE\s*\{'
            r'[^}]*?VALUE="([^"]+)"', text):
        alias, tag = m.group(1), m.group(2)
        if tag and alias not in out:
            out[alias] = {'tag': tag, 'unit': unit_at(m.start())}
    return out


def _alias_definitions(text):
    """alias name -> description/purpose, from ALIAS_DEFINITION blocks."""
    out = {}
    for m in re.finditer(
            r'ALIAS_DEFINITION NAME="([A-Za-z0-9_\-]+)"\s*\{([^}]*)\}', text):
        body = m.group(2)
        d = re.search(r'DESCRIPTION="([^"]*)"', body)
        p = re.search(r'PURPOSE=([A-Z_]+)', body)
        out[m.group(1)] = {'desc': d.group(1) if d else '',
                           'purpose': p.group(1) if p else ''}
    return out


def _em_member_bindings(text):
    """(instance_tag, member) -> module tag, from MODULE_BLOCK_RESOLUTION, plus a
    reverse index module_tag -> [(instance_tag, member)]."""
    rev = {}
    for im in re.finditer(
            r'MODULE_INSTANCE TAG="([^"]+)" PLANT_AREA="[^"]*" MODULE_CLASS="([^"]+)"'
            r'(.*?)(?=\nMODULE_INSTANCE |\Z)', text, re.DOTALL):
        inst, cls, blk = im.group(1), im.group(2), im.group(3)
        for rm in re.finditer(
                r'MODULE_BLOCK_RESOLUTION NAME="([^"]+)"\s*\{\s*MODULE="([^"]*)"', blk):
            member, mod = rm.group(1), rm.group(2)
            if mod:
                rev.setdefault(mod, []).append({'instance': inst, 'class': cls,
                                                'member': member})
    return rev


# ── phase/recipe expression usage of an alias or member name ────────────────
_PHASE_HDR = re.compile(
    r'(PHASE|MODULE_CLASS|MODULE_INSTANCE|COMPOSITE_TEMPLATE)[^"\n]*'
    r'NAME="([^"]+)"|TAG="([^"]+)"')


def _find_expression_uses(text, name, owner_hint=None):
    """Every place ^/name/ appears in an expression, with the enclosing object and,
    when discoverable, the step/transition + snippet. If owner_hint is given (we know
    which EM instance/phase owns these references), we attribute uses to it directly
    and only search within its block, which is both faster and accurate."""
    uses = []
    pat = re.compile(r"\^/" + re.escape(name) + r"/([A-Za-z0-9_.$]+)")

    if owner_hint:
        # restrict to the owner's block so attribution + step lookup are exact
        blk, base = _object_block(text, owner_hint)
        scope = blk if blk else text
        offset = base if blk else 0
        owner_name = owner_hint
    else:
        scope = text
        offset = 0
        owner_name = None

    # step/transition attribution within the scope
    step_re = re.compile(r'(STEP|TRANSITION)\s+NAME="([^"]+)"')
    steps = [(m.start(), m.group(1), m.group(2)) for m in step_re.finditer(scope)]
    steps.sort()

    def step_at(pos):
        lo, hi, ans = 0, len(steps) - 1, None
        while lo <= hi:
            mid = (lo + hi) // 2
            if steps[mid][0] <= pos:
                ans = steps[mid]; lo = mid + 1
            else:
                hi = mid - 1
        return ans

    # global header index for the no-hint (direct/alias) case — include the common
    # DeltaV container keywords so a use can be attributed to its owning object.
    headers = []
    if not owner_hint:
        for m in re.finditer(
                r'(?:PHASE_CLASS|EQUIPMENT_PHASE|MODULE_CLASS|MODULE_INSTANCE|'
                r'COMPOSITE_TEMPLATE|UNIT_CLASS)\b[^\n]*?(?:NAME|TAG)="([^"]+)"', text):
            headers.append((m.start(), m.group(1)))
        headers.sort()

    def owner_at(pos):
        if owner_name:
            return owner_name
        lo, hi, ans = 0, len(headers) - 1, '?'
        while lo <= hi:
            mid = (lo + hi) // 2
            if headers[mid][0] <= pos:
                ans = headers[mid][1]; lo = mid + 1
            else:
                hi = mid - 1
        return ans

    seen = set()
    for m in pat.finditer(scope):
        pos = m.start()
        param = m.group(1)
        st = step_at(pos)
        s = scope[max(0, pos - 40):pos + 60].replace('\n', ' ').strip()
        key = (st[2] if st else '', param)
        if key in seen:
            continue
        seen.add(key)
        uses.append({
            'owner': owner_at(pos),
            'step_kind': st[1] if st else '',
            'step': st[2] if st else '',
            'param': param,
            'snippet': _clean_snippet(s),
        })
    return uses


def _object_block(text, tag_or_name):
    """Return (block_text, start_offset) for a MODULE_INSTANCE/MODULE_CLASS by tag/name,
    so we can scope a search to just that object."""
    for pat in (r'MODULE_INSTANCE TAG="' + re.escape(tag_or_name) + r'"',
                r'MODULE_CLASS NAME="' + re.escape(tag_or_name) + r'"'):
        m = re.search(pat, text)
        if m:
            start = m.start()
            nxt = re.search(r'\n(?:MODULE_INSTANCE |MODULE_CLASS )', text[start + 1:])
            end = (start + 1 + nxt.start()) if nxt else len(text)
            return text[start:end], start
    return None, 0


def _clean_snippet(s):
    # keep it tidy and short
    s = re.sub(r'\s+', ' ', s)
    return s[:110]


def _dynamic_bindings(text):
    """Dynamic parameter bindings: D_XXX.$REF := "//" + <var> + "<suffix>".
    These resolve a path at runtime, so a module referenced this way is invisible to
    static search. We capture each bind's literal suffix (e.g. '-HS-001/PV') and the
    variable part, so a module whose tag/path matches the suffix can be surfaced."""
    out = []
    for m in re.finditer(
            r"'?\^?/?(D_[A-Za-z0-9_]+)\.\$REF'?\s*:=\s*"
            r"((?:[^;]*?(?:\"\"[^\"]*\"\")?)+?)(?:;|DELAY|CONFIRM|\Z)", text):
        param = m.group(1)
        expr = m.group(2)
        lits = re.findall(r'""([^"]*)""', expr)
        var = ''
        vm = re.search(r"'(\^?/?[A-Za-z0-9_.]+)'", expr)
        if vm:
            var = vm.group(1)
        suffix = ''.join(x for x in lits if x not in ('//', '/'))
        if not suffix:
            continue
        out.append({'param': param, 'var': var, 'suffix': suffix,
                    'expr': _clean_snippet(expr)})
    return out


# ── main entry ───────────────────────────────────────────────────────────────
def trace_module(text, module_tag, param=None, max_uses_per_path=40):
    """Find every reference to a module (optionally a specific parameter), across
    direct/alias/EM-member layers, each with its resolution path.

    Returns:
      {
        'module': tag, 'param': param or None,
        'summary': {'direct':n,'alias':n,'em_member':n,'total':n},
        'findings': [
           {'via':'alias'|'em_member'|'direct',
            'link': '<alias or member name>',
            'link_desc': '...',
            'path': 'human readable resolution path',
            'uses': [ {owner, step_kind, step, param, snippet} ... ] }
        ]
      }
    """
    findings = []
    aliases = _alias_bindings(text)
    alias_defs = _alias_definitions(text)
    em_rev = _em_member_bindings(text)

    def _match_param(uses):
        if not param:
            return uses
        pl = param.lower().lstrip('.')
        return [u for u in uses if pl in (u['param'] or '').lower()]

    # 1. ALIAS layer — a unit alias (ALIAS_RESOLUTION) bound to this module. Phases
    #    reference the alias name; the alias->tag link lives on the unit, which is why
    #    DeltaV can't surface this from the module side.
    for alias, bind in aliases.items():
        if bind['tag'] != module_tag:
            continue
        uses = _match_param(_find_expression_uses(text, alias))
        info = alias_defs.get(alias, {})
        unit = bind.get('unit', '')
        findings.append({
            'via': 'alias',
            'link': alias,
            'link_desc': info.get('desc', '') or 'unit alias',
            'purpose': info.get('purpose', ''),
            'path': (f'phase logic → alias “{alias}”'
                     + (f' (resolved on unit {unit})' if unit else '')
                     + f' → module {module_tag}'),
            'unit': unit,
            'uses': uses[:max_uses_per_path],
            'use_count': len(uses),
        })

    # 2. EM member resolution layer — the member is referenced in the EM *class* SFC
    #    (the deployed instance only holds the resolution). Scope the search to the
    #    class block, but report the instance the resolution belongs to.
    for binding in em_rev.get(module_tag, []):
        member = binding['member']
        uses = _match_param(_find_expression_uses(text, member,
                                                  owner_hint=binding['class']))
        # relabel owner to the class for clarity
        for u in uses:
            u['owner'] = binding['class']
        findings.append({
            'via': 'em_member',
            'link': member,
            'link_desc': f"resolved on EM instance {binding['instance']} "
                         f"(class {binding['class']})",
            'path': f"EM class {binding['class']} SFC → member “{member}” "
                    f"→ resolved on {binding['instance']} → module {module_tag}",
            'instance': binding['instance'],
            'em_class': binding['class'],
            'uses': uses[:max_uses_per_path],
            'use_count': len(uses),
        })

    # 3. DYNAMIC PARAMETER layer — a D_XXX.$REF binds a runtime path like
    #    "//" + <skid var> + "-HS-001/PV". A module whose tag ends in that suffix's
    #    tag portion is referenced here, but only resolvable at runtime — completely
    #    invisible to static search. Surface the binding + where the D_ param is used.
    dyn = _dynamic_bindings(text)
    seen_dyn = set()
    for db in dyn:
        # the suffix's leading tag part, e.g. '-HS-001/PV' -> tag ends with '-HS-001'
        suf = db['suffix']
        tag_part = suf.split('/')[0].lstrip('-')          # 'HS-001'
        sfx_param = suf.split('/', 1)[1] if '/' in suf else ''
        if not tag_part:
            continue
        # module matches if its tag ends with the suffix tag part
        if not module_tag.upper().endswith(tag_part.upper()):
            continue
        # optional parameter filter: the dynamic ref targets a specific param
        if param and sfx_param and param.lower().lstrip('.') not in sfx_param.lower():
            continue
        if db['param'] in seen_dyn:
            continue
        seen_dyn.add(db['param'])
        uses = _find_expression_uses(text, db['param'])
        var_txt = db['var'] or 'a recipe/unit value'
        findings.append({
            'via': 'dynamic',
            'link': db['param'],
            'link_desc': 'dynamic reference (.$REF resolved at runtime)',
            'path': f"dynamic param “{db['param']}”.$REF := \"//\" + {var_txt} + "
                    f"\"{suf}\" → resolves to a module ending in {tag_part}"
                    + (f" ({sfx_param})" if sfx_param else ""),
            'dynamic_expr': db['expr'],
            'resolves_via': var_txt,
            'uses': uses[:max_uses_per_path],
            'use_count': max(len(uses), 1),   # the bind itself counts as a reference
        })

    # 4. DIRECT layer — the tag used literally in expressions (rare but real)
    direct_uses = _match_param(_find_expression_uses(text, module_tag))
    if direct_uses:
        findings.append({
            'via': 'direct',
            'link': module_tag,
            'link_desc': 'direct tag reference',
            'path': f'expression references {module_tag} directly',
            'uses': direct_uses[:max_uses_per_path],
            'use_count': len(direct_uses),
        })

    # drop findings that resolved to zero actual uses (binding exists but unused)
    non_empty = [f for f in findings if f['use_count'] > 0]

    summary = {'alias': sum(1 for f in non_empty if f['via'] == 'alias'),
               'em_member': sum(1 for f in non_empty if f['via'] == 'em_member'),
               'dynamic': sum(1 for f in non_empty if f['via'] == 'dynamic'),
               'direct': sum(1 for f in non_empty if f['via'] == 'direct')}
    summary['total_uses'] = sum(f['use_count'] for f in non_empty)
    summary['paths'] = len(non_empty)

    return {'module': module_tag, 'param': param,
            'summary': summary,
            'findings': sorted(non_empty, key=lambda f: -f['use_count']),
            'unused_bindings': [{'via': f['via'], 'link': f['link']}
                                for f in findings if f['use_count'] == 0]}


def module_suggestions(text, q, limit=20):
    """Autocomplete: module tags matching a query, for the tracer search box."""
    q = (q or '').upper()
    tags = set()
    for m in re.finditer(r'MODULE_INSTANCE TAG="([^"]+)"', text):
        t = m.group(1)
        if not q or q in t.upper():
            tags.add(t)
        if len(tags) > 400:
            break
    out = sorted(tags)
    if q:
        out.sort(key=lambda t: (not t.upper().startswith(q), t))
    return out[:limit]
