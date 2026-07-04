/* device_sim.js — browser twin of device_sim.py.
   Models command -> (travel delay) -> feedback for field devices so the phase/EM
   simulator can run closed-loop and animate device glyphs. Kept in lockstep with
   the Python version (mirror-with-delay; no fault injection yet). */
(function(global){
  var VALVE_2STATE='valve_2state', VALVE_ANALOG='valve_analog', MOTOR='motor', PUMP='pump', GENERIC='generic';
  var DEFAULT_TIMES={valve_2state:2.0, valve_analog:4.0, motor:3.0, pump:3.0, generic:1.0};

  function classify(subType, cls){
    var s=((subType||'')+' '+(cls||'')).toUpperCase();
    if(s.indexOf('VALVE')>=0 && (s.indexOf('2STATE')>=0||s.indexOf('2_STATE')>=0||s.indexOf('DIG')>=0)) return VALVE_2STATE;
    if(s.indexOf('VALVE')>=0 && (s.indexOf('ANLG')>=0||s.indexOf('ANALOG')>=0||s.indexOf('POS')>=0)) return VALVE_ANALOG;
    if(s.indexOf('MTR')>=0||s.indexOf('MOTOR')>=0) return MOTOR;
    if(s.indexOf('PMP')>=0||s.indexOf('PUMP')>=0) return PUMP;
    if(s.indexOf('VALVE')>=0) return VALVE_2STATE;
    return GENERIC;
  }

  function newState(family, tag, role, travel){
    var discrete=(family===VALVE_2STATE||family===MOTOR||family===PUMP);
    var init = family===VALVE_2STATE ? 'CLOSED' : ((family===MOTOR||family===PUMP)?'STOPPED':0.0);
    return {tag:tag||'', role:role||'', family:family,
      travel: travel==null?(DEFAULT_TIMES[family]||1.0):travel,
      target:init, pv:init, discrete:discrete, moving:false, elapsed:0.0};
  }

  function normDiscrete(family, cmd){
    var c=String(cmd).trim().toUpperCase();
    if(family===VALVE_2STATE){
      if(['OPEN','OPENED','TRUE','1','ON'].indexOf(c)>=0) return 'OPEN';
      if(['CLOSE','CLOSED','FALSE','0','OFF'].indexOf(c)>=0) return 'CLOSED';
    }
    if(family===MOTOR||family===PUMP){
      if(['START','RUN','RUNNING','ON','TRUE','1'].indexOf(c)>=0) return 'RUNNING';
      if(['STOP','STOPPED','OFF','FALSE','0'].indexOf(c)>=0) return 'STOPPED';
    }
    return null;
  }

  function command(state, cmd){
    if(state.discrete){
      var tgt=normDiscrete(state.family, cmd);
      if(tgt!=null && tgt!==state.target){ state.target=tgt; state.moving=true; state.elapsed=0.0; }
    } else {
      var f=parseFloat(cmd);
      if(!isNaN(f) && f!==state.target){ state.target=f; state.moving=true; state.elapsed=0.0; delete state._rampStart; }
    }
    return state;
  }

  function advance(state, dt){
    if(!state.moving) return state;
    state.elapsed=(state.elapsed||0)+dt;
    var travel=Math.max(0.001, state.travel||1.0);
    if(state.discrete){
      if(state.elapsed>=travel){ state.pv=state.target; state.moving=false; }
    } else {
      if(state._rampStart==null) state._rampStart=state.pv;
      var frac=Math.min(1.0, state.elapsed/travel);
      state.pv=state._rampStart+(state.target-state._rampStart)*frac;
      if(frac>=1.0){ state.pv=state.target; state.moving=false; delete state._rampStart; }
    }
    return state;
  }

  function feedback(state){ return state.pv; }
  function settled(state){ return !state.moving; }

  function glyphState(state){
    var fam=state.family, pv=state.pv;
    if(fam===VALVE_2STATE) return {kind:'valve', open:pv==='OPEN', moving:state.moving, color:pv==='OPEN'?'green':'gray', label:String(pv)};
    if(fam===MOTOR||fam===PUMP){ var r=pv==='RUNNING'; return {kind:fam, running:r, moving:state.moving, color:r?'green':'red', label:String(pv)}; }
    if(fam===VALVE_ANALOG){ var p=parseFloat(pv)||0; return {kind:'analog_valve', pct:p, moving:state.moving, color:p>1?'green':'gray', label:p.toFixed(0)+'%'}; }
    return {kind:'generic', label:String(pv), color:'gray', moving:false};
  }

  var api={VALVE_2STATE:VALVE_2STATE,VALVE_ANALOG:VALVE_ANALOG,MOTOR:MOTOR,PUMP:PUMP,GENERIC:GENERIC,
    classify:classify,newState:newState,command:command,advance:advance,feedback:feedback,settled:settled,glyphState:glyphState};
  if(typeof module!=='undefined'&&module.exports) module.exports=api;
  global.DeviceSim=api;
})(typeof window!=='undefined'?window:this);
