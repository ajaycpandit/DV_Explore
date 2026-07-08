"""alias_validator.py — a commissioning/validation "unit tool" (#10).

For each deployed unit instance, cross-check the #aliases# actually used in its
phases' logic against the unit's alias resolution table, and flag problems that
matter during commissioning and Part 11 review:

  * UNRESOLVED — an alias used in phase logic has no resolution in the unit table
    (the phase references a device the unit never wires up).
  * IGNORED-BUT-USED — the alias is marked ignore=true in the unit table yet the
    phase logic still reads/writes it (a likely mis-commissioning).
  * RESOLVED-TO-MISSING — the alias resolves to a device tag that isn't a known
    deployed module in this export (dangling reference).
  * UNUSED — declared/resolved in the unit table but never referenced by any of the
    unit's phases (dead alias; informational, not an error).

This reuses the exact resolution the simulator uses (sim_aliases / sim_run), so the
validator and the interactive walk agree. Pure analysis over the parsed model; no
core changes.
"""

import db_parser


def _phase_alias_usage(text, phase_name):
    """Set of alias names referenced by one phase's SFC logic (steps/actions/trans)."""
    try:
        import sim_run
        import sim_aliases
        sim = sim_run.PhaseSim(text, phase_name)
        used = sim_aliases.aliases_used(
            sim.order, sim.actions,
            {tn: sim.trans.get(tn, '') for tn in sim.trans})
        return set(used) - {'THISUNIT'}
    except Exception:
        return set()


def validate_export(text, catalog=None):
    """Return a per-unit validation report:

    {
      'units': [ { 'unit', 'cls', 'phase_count', 'alias_count',
                   'issues': [ {'severity','kind','alias','phase','detail'} ],
                   'counts': {'unresolved','ignored_used','missing_module','unused'} } ],
      'totals': {...}
    }
    """
    if catalog is None:
        catalog = db_parser.parse_database(text)
    unit_instances = catalog.get('unit_instances', {}) or {}
    unit_class_phases = catalog.get('unit_class_phases', {}) or {}
    deployed = catalog.get('deployed_modules', {}) or {}
    deployed_tags = set(deployed.keys())

    units_out = []
    totals = {'unresolved': 0, 'ignored_used': 0, 'missing_module': 0, 'unused': 0,
              'units_with_issues': 0}

    for uname, uinfo in sorted(unit_instances.items()):
        cls = uinfo.get('cls', '')
        phases = unit_class_phases.get(cls, []) or []
        raw_aliases = uinfo.get('aliases', []) or []
        # normalize the unit alias table to {name: {value, desc, ignore}}
        table = {}
        for a in raw_aliases:
            if isinstance(a, dict) and a.get('alias'):
                table[a['alias']] = {
                    'value': a.get('value', ''),
                    'desc': a.get('desc', ''),
                    'ignore': bool(a.get('ignore', False)),
                }
        # which aliases each phase uses
        used_by_phase = {}
        all_used = set()
        for ph in phases:
            u = _phase_alias_usage(text, ph)
            used_by_phase[ph] = u
            all_used |= u

        issues = []
        counts = {'unresolved': 0, 'ignored_used': 0, 'missing_module': 0, 'unused': 0}

        for ph in phases:
            for alias in sorted(used_by_phase.get(ph, set())):
                rec = table.get(alias)
                if rec is None:
                    issues.append({'severity': 'error', 'kind': 'unresolved',
                                   'alias': alias, 'phase': ph,
                                   'detail': 'used in phase logic but not resolved in the unit alias table'})
                    counts['unresolved'] += 1
                elif rec.get('ignore'):
                    issues.append({'severity': 'warn', 'kind': 'ignored_used',
                                   'alias': alias, 'phase': ph,
                                   'detail': 'alias is marked Ignore in the unit table but the phase logic still references it'})
                    counts['ignored_used'] += 1
                else:
                    dev = rec.get('value', '')
                    if dev and dev not in deployed_tags:
                        issues.append({'severity': 'warn', 'kind': 'missing_module',
                                       'alias': alias, 'phase': ph,
                                       'detail': f'resolves to "{dev}", which is not a deployed module in this export'})
                        counts['missing_module'] += 1

        # unused aliases (declared/resolved but never referenced) — informational
        for alias, rec in sorted(table.items()):
            if alias not in all_used and not rec.get('ignore'):
                issues.append({'severity': 'info', 'kind': 'unused',
                               'alias': alias, 'phase': '',
                               'detail': f'resolved to "{rec.get("value","")}" but not referenced by any phase in this unit'})
                counts['unused'] += 1

        for k in ('unresolved', 'ignored_used', 'missing_module', 'unused'):
            totals[k] += counts[k]
        if counts['unresolved'] or counts['ignored_used'] or counts['missing_module']:
            totals['units_with_issues'] += 1

        units_out.append({
            'unit': uname, 'cls': cls,
            'phase_count': len(phases), 'alias_count': len(table),
            'issues': issues, 'counts': counts,
        })

    return {'units': units_out, 'totals': totals}


def build_report_html(text, catalog=None):
    """Render the validation report as explorer-styled HTML (collapsible per unit)."""
    import html as _h
    rep = validate_export(text, catalog)
    t = rep['totals']

    def esc(s):
        return _h.escape(str(s if s is not None else ''))

    sev_badge = {
        'error': '<span class="av-sev av-err">ERROR</span>',
        'warn': '<span class="av-sev av-warn">WARN</span>',
        'info': '<span class="av-sev av-info">INFO</span>',
    }
    kind_label = {
        'unresolved': 'Unresolved', 'ignored_used': 'Ignored but used',
        'missing_module': 'Missing module', 'unused': 'Unused',
    }

    parts = ['<div class="av-report">']
    parts.append(
        '<div class="av-summary">'
        f'<span class="av-chip av-err-c">{t["unresolved"]} unresolved</span>'
        f'<span class="av-chip av-warn-c">{t["ignored_used"]} ignored-but-used</span>'
        f'<span class="av-chip av-warn-c">{t["missing_module"]} missing-module</span>'
        f'<span class="av-chip av-info-c">{t["unused"]} unused</span>'
        f'<span class="av-chip">{t["units_with_issues"]} unit(s) with issues</span>'
        '</div>')

    if not rep['units']:
        parts.append('<p class="empty">No deployed unit instances with phases were found.</p>')
        parts.append('</div>')
        return ''.join(parts)

    for u in rep['units']:
        c = u['counts']
        has_err = c['unresolved'] or c['ignored_used'] or c['missing_module']
        dot = 'av-dot-err' if c['unresolved'] else ('av-dot-warn' if has_err else 'av-dot-ok')
        collapsed = '' if has_err else ' collapsed'
        parts.append(f'<div class="av-unit av-collapse{collapsed}">')
        parts.append(
            f'<h4><span class="av-dot {dot}"></span>{esc(u["unit"])} '
            f'<span class="av-sub">{esc(u["cls"])} \u00b7 {u["phase_count"]} phase(s) \u00b7 '
            f'{u["alias_count"]} alias(es)</span>'
            f'<span class="av-unit-counts">'
            f'{c["unresolved"]}E / {c["ignored_used"] + c["missing_module"]}W / {c["unused"]}I'
            f'</span></h4>')
        if u['issues']:
            parts.append('<table class="av-tbl"><thead><tr>'
                         '<th>Severity</th><th>Issue</th><th>Alias</th><th>Phase</th>'
                         '<th>Detail</th></tr></thead><tbody>')
            # errors/warnings first, then info
            order = {'error': 0, 'warn': 1, 'info': 2}
            for it in sorted(u['issues'], key=lambda x: (order.get(x['severity'], 3), x['kind'], x['alias'])):
                parts.append(
                    f'<tr class="av-row-{esc(it["severity"])}">'
                    f'<td>{sev_badge.get(it["severity"], "")}</td>'
                    f'<td>{esc(kind_label.get(it["kind"], it["kind"]))}</td>'
                    f'<td class="av-alias">{esc(it["alias"])}</td>'
                    f'<td>{esc(it["phase"])}</td>'
                    f'<td class="av-detail">{esc(it["detail"])}</td></tr>')
            parts.append('</tbody></table>')
        else:
            parts.append('<div class="av-clean">No alias issues \u2014 every alias used by this unit\u2019s '
                         'phases resolves to a deployed module.</div>')
        parts.append('</div>')
    parts.append('</div>')
    return ''.join(parts)
