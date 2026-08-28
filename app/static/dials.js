'use strict';
(function(){
  try {
    var BOX = document.getElementById('fluid-dialers');
    if (!BOX) return;

    // wait for fluid to be ready; retry a few times if loaded before fluid.js
    var ATTEMPTS = 0;
    function init() {
      var fluid = window.catnewsFluid;
      if (!fluid || !fluid.config) {
        if (ATTEMPTS++ < 40) return setTimeout(init, 100);
        return;
      }
      var config = fluid.config;
      var STORAGE_KEY = 'catnews:fluid-dials-v2';
      var MAP = {
        splat:    { cfg:'SPLAT_RADIUS', inputId:'dial-splat', min:0.01, max:0.12, step:0.005, def:0.010 },
        density:  { cfg:'DENSITY_DISSIPATION', inputId:'dial-density', min:0.90, max:1.0, step:0.005, def:0.925 },
        curl:     { cfg:'CURL', inputId:'dial-curl', min:0, max:50, step:1, def:0 },
        pressure: { cfg:'PRESSURE_ITERATIONS', inputId:'dial-pressure', min:0, max:30, step:1, def:20 },
        bloom:    { cfg:'BLOOM_INTENSITY', inputId:'dial-bloom', min:0, max:1.2, step:0.05, def:0.30 }
      };
      var dials = {};
      var persistTimer = null;
      function clamp(v, lo, hi){ return Math.min(hi, Math.max(lo, v)); }
      function snap(v, step, min){
        var n = Math.round((v - min)/step);
        return +(min + n*step).toFixed(4);
      }
      function loadStored(){
        try{ var raw=localStorage.getItem(STORAGE_KEY); if(raw) return JSON.parse(raw);}catch(e){}
        return {};
      }
      function saveStored(){
        clearTimeout(persistTimer);
        persistTimer = setTimeout(function(){
          var obj={};
          Object.keys(dials).forEach(function(k){ obj[k]=dials[k].value; });
          try{ localStorage.setItem(STORAGE_KEY, JSON.stringify(obj)); }catch(e){}
        }, 120);
      }
      function angleFor(value, min, max){
        var t = (value - min)/(max - min);
        return -135 + t*270;
      }
      function pctFor(value, min, max){
        return ((value - min)/(max - min))*100;
      }
      function setDial(key, value, opts){
        var meta = MAP[key];
        if(!meta) return;
        value = clamp(snap(+value, meta.step, meta.min), meta.min, meta.max);
        if (!dials[key]) return;
        dials[key].value = value;
        try {
          if(meta.cfg==='SPLAT_RADIUS') fluid.setConfig('SPLAT_RADIUS', value * 14);
          else fluid.setConfig(meta.cfg, value);
        } catch(e){
          if(meta.cfg==='SPLAT_RADIUS') config.SPLAT_RADIUS = value * 14;
          else config[meta.cfg] = value;
        }
        var knob = dials[key].knob;
        var pct = pctFor(value, meta.min, meta.max);
        if(knob) {
          knob.style.setProperty('--dial-angle', angleFor(value, meta.min, meta.max)+'deg');
          knob.style.setProperty('--dial-pct', pct + '%');
        }
        if(knob){
          knob.setAttribute('aria-valuenow', String(value));
          knob.setAttribute('aria-valuetext', String(value));
          knob.setAttribute('aria-valuemin', String(meta.min));
          knob.setAttribute('aria-valuemax', String(meta.max));
        }
        var valEl = dials[key].valEl;
        if(valEl) {
          valEl.textContent = (meta.step < 0.01 ? value.toFixed(3) : meta.step < 1 ? value.toFixed(2) : String(Math.round(value)));
          valEl.style.setProperty('--dial-pct', pct + '%');
        }
        var wrap = dials[key].wrap;
        if(wrap) {
          wrap.setAttribute('data-value', String(value));
          wrap.style.setProperty('--dial-pct', pct + '%');
        }
        var range = dials[key].range;
        if(range && String(range.value)!==String(value)) range.value = String(value);
        if(!opts || !opts.silent) saveStored();
      }

      var stored = loadStored();
      BOX.querySelectorAll('.dial[data-key]').forEach(function(wrap){
        var key = wrap.getAttribute('data-key');
        var meta = MAP[key];
        if(!meta) return;
        var range = document.getElementById(meta.inputId);
        var knob = wrap.querySelector('.dial-knob');
        var valEl = wrap.querySelector('.dial-value');
        var initial = stored[key] != null ? stored[key] : (range ? parseFloat(range.value) : meta.def);
        if(isNaN(initial)) initial = meta.def;
        dials[key] = { wrap:wrap, knob:knob, valEl:valEl, range:range, value:initial };
        setDial(key, initial, {silent:true});
        if(range){
          range.addEventListener('input', function(){ setDial(key, parseFloat(range.value)); });
        }
        if(knob){
          (function(key, knob, meta){
            var dragging=false, startY=0, startX=0, startVal=0, activePointerId=null, activeEl=null, isTrack=false;
            function valueFromX(clientX){
              var rect = knob.getBoundingClientRect();
              var pct = (clientX - rect.left) / rect.width;
              pct = Math.max(0, Math.min(1, pct));
              return meta.min + pct * (meta.max - meta.min);
            }
            function onDown(e){
              try{ e.preventDefault(); }catch(_e){}
              dragging=true;
              var el = e.currentTarget;
              activeEl = el;
              isTrack = (el === knob);
              if(el.setPointerCapture && e.pointerId!=null) try{ el.setPointerCapture(e.pointerId);}catch(_e){}
              activePointerId = e.pointerId;
              startY = e.clientY != null ? e.clientY : (e.touches && e.touches[0] ? e.touches[0].clientY : 0);
              startX = e.clientX != null ? e.clientX : (e.touches && e.touches[0] ? e.touches[0].clientX : 0);
              startVal = dials[key].value;
              // if clicking directly on track, jump to click position
              if(isTrack && e.clientX != null){
                setDial(key, valueFromX(e.clientX));
                // update start so drag continues from new position
                startVal = dials[key].value;
                startX = e.clientX;
                startY = e.clientY;
              }
              el.style.cursor='grabbing';
              try{ knob.focus(); }catch(_e){}
            }
            function onMove(e){
              if(!dragging) return;
              if(isTrack){
                var x = e.clientX != null ? e.clientX : (e.touches && e.touches[0] ? e.touches[0].clientX : null);
                if(x==null) return;
                // horizontal drag on track is direct mapping, not delta
                setDial(key, valueFromX(x));
              } else {
                var y = e.clientY != null ? e.clientY : (e.touches && e.touches[0] ? e.touches[0].clientY : null);
                if(y==null) return;
                var dy = startY - y;
                var rangeSpan = meta.max - meta.min;
                var delta = (dy / 160) * rangeSpan;
                setDial(key, startVal + delta);
              }
            }
            function onUp(e){
              if(!dragging) return;
              dragging=false;
              if(activeEl) activeEl.style.cursor='';
              knob.style.cursor='';
              if(activeEl && activePointerId!=null && activeEl.releasePointerCapture) try{ activeEl.releasePointerCapture(activePointerId);}catch(_e){}
              activeEl=null;
              isTrack=false;
            }
            function attach(el){
              if(!el) return;
              el.addEventListener('pointerdown', onDown);
              el.addEventListener('wheel', function(e){
                e.preventDefault();
                var dir = e.deltaY < 0 ? 1 : -1;
                setDial(key, dials[key].value + dir*meta.step);
              }, {passive:false});
            }
            attach(knob);
            attach(valEl);
            attach(wrap);
            window.addEventListener('pointermove', onMove);
            window.addEventListener('pointerup', onUp);
            window.addEventListener('pointercancel', onUp);
            knob.addEventListener('keydown', function(e){
              if(e.key==='ArrowLeft' || e.key==='ArrowDown'){ e.preventDefault(); setDial(key, dials[key].value - meta.step); }
              else if(e.key==='ArrowRight' || e.key==='ArrowUp'){ e.preventDefault(); setDial(key, dials[key].value + meta.step); }
              else if(e.key==='Home'){ e.preventDefault(); setDial(key, meta.min); }
              else if(e.key==='End'){ e.preventDefault(); setDial(key, meta.max); }
            });
            if(valEl){
              valEl.setAttribute('tabindex','0');
              valEl.setAttribute('role','slider');
              valEl.addEventListener('keydown', function(e){
                if(e.key==='ArrowLeft' || e.key==='ArrowDown'){ e.preventDefault(); setDial(key, dials[key].value - meta.step); }
                else if(e.key==='ArrowRight' || e.key==='ArrowUp'){ e.preventDefault(); setDial(key, dials[key].value + meta.step); }
              });
            }
          })(key, knob, meta);
        }
      });
      Object.keys(dials).forEach(function(k){ setDial(k, dials[k].value, {silent:true}); });
      var resetBtn = document.getElementById('dial-reset');
      if(resetBtn){
        resetBtn.addEventListener('click', function(){
          Object.keys(MAP).forEach(function(k){ setDial(k, MAP[k].def); });
        });
      }
      window.catnewsFluidDials = {
        set: setDial,
        get: function(k){ return dials[k] ? dials[k].value : null; },
        box: BOX
      };
    }

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', init);
    } else {
      init();
    }
  } catch(err) {
    console.warn('catnews dials init failed', err);
  }
})();
