(() => {
  'use strict';
  const canvas = document.getElementById('loginGlbCanvas');
  const status = document.getElementById('loginGlbStatus');
  if (!canvas) return;

  const setError = (msg) => {
    console.error('[LoginGlbViewer]', msg);
    status?.classList.add('is-error');
    if (status && status.lastElementChild) status.lastElementChild.textContent = msg;
  };

  const contextOptions = { antialias: true, alpha: true, powerPreference: 'high-performance' };
  let gl = null;
  let isWebGL2 = false;
  try {
    gl = canvas.getContext('webgl2', contextOptions);
    isWebGL2 = Boolean(gl);
  } catch (_) {}
  if (!gl) {
    try { gl = canvas.getContext('webgl', contextOptions) || canvas.getContext('experimental-webgl', contextOptions); } catch (_) {}
  }
  const reduceMotion = Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);

  const startCanvas2DFallback = () => {
    let ctx = null;
    try { ctx = canvas.getContext('2d'); } catch (_) {}
    if (!ctx) return false;

    api.ready = true;
    api.readyAt = performance.now();
    canvas.classList.add('is-ready');
    status?.classList.add('is-ready');

    let fallbackStart = performance.now();
    let heat = 0, interaction = 0, spin = 0;
    const pts = Array.from({length: 112}, (_,i) => {
      const a = (i * 2.399963229728653) % (Math.PI*2);
      const rr = .30 + ((i * 37) % 100) / 100 * .62;
      return {a, rr, r: 1.5 + (i % 5) * .55};
    });

    const gearPath = (cx,cy,r0,r1,teeth,rot) => {
      ctx.beginPath();
      for(let i=0;i<teeth*4;i++){
        const a=rot+i*Math.PI*2/(teeth*4);
        const r=(i%4===1||i%4===2)?r1:r0;
        const x=cx+Math.cos(a)*r, y=cy+Math.sin(a)*r;
        if(i===0) ctx.moveTo(x,y); else ctx.lineTo(x,y);
      }
      ctx.closePath();
    };

    const draw = (now) => {
      const loginScreen=canvas.closest('.login-screen');
      if(document.hidden||loginScreen?.classList.contains('hidden')){requestAnimationFrame(draw);return;}
      const dpr=Math.min(devicePixelRatio||1,2);
      const w=Math.max(1,canvas.clientWidth*dpr|0), h=Math.max(1,canvas.clientHeight*dpr|0);
      if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}
      ctx.setTransform(dpr,0,0,dpr,0,0);
      const cw=canvas.clientWidth,ch=canvas.clientHeight,cx=cw*.5,cy=ch*.5;
      ctx.clearRect(0,0,cw,ch);

      const rect=canvas.getBoundingClientRect();
      const rad=Math.max(92,Math.min(innerWidth,innerHeight,rect.height)*.255);
      const dx=(api.pointerClientX-(rect.left+rect.width*.5))/rad;
      const dy=(api.pointerClientY-(rect.top+rect.height*.5))/(rad*.98);
      const hovering=api.pointerSeen&&!api.entering&&!reduceMotion&&(dx*dx+dy*dy<=1);
      interaction += ((hovering?1:0)-interaction) * (hovering ? .095 : .052);
      heat=Math.max(0,Math.min(.68,heat+(hovering?1.8:-4.8)/1200));
      if (!reduceMotion) spin += .0018 + interaction*.0065 + heat*heat*.012;

      const s0=Math.min(cw,ch)*.17;
      ctx.save();
      ctx.translate(cx,cy);

      const ring=(rx,ry,ang,lineWidth,alpha)=>{
        ctx.save();ctx.rotate(ang);ctx.beginPath();ctx.ellipse(0,0,rx,ry,0,0,Math.PI*2);
        ctx.strokeStyle=`rgba(70,160,215,${alpha})`;ctx.lineWidth=lineWidth;ctx.stroke();ctx.restore();
      };
      const t=reduceMotion ? 0 : (now-fallbackStart)*.001;
      ring(s0*1.95,s0*.58,.45+interaction*.20*Math.sin(t*.62),6, .48);
      ring(s0*1.63,s0*.49,-.68+interaction*.25*Math.sin(t*.96+.7),4.5, .58);
      ring(s0*2.18,s0*.68,1.02+interaction*.28*Math.sin(t*.48+1.4),3.5, .40);

      ctx.rotate(spin);
      gearPath(0,0,s0*.83,s0,28,0);
      const g=ctx.createRadialGradient(-s0*.18,-s0*.22,s0*.10,0,0,s0);
      g.addColorStop(0,'#f5f9fd');g.addColorStop(.34,'#93a6bc');g.addColorStop(.68,'#4477ae');g.addColorStop(1,'#0d2e52');
      ctx.fillStyle=g;ctx.fill();

      ctx.globalCompositeOperation='destination-out';
      ctx.beginPath();ctx.arc(0,0,s0*.45,0,Math.PI*2);ctx.fill();
      ctx.globalCompositeOperation='source-over';

      ctx.shadowBlur=16+heat*24;ctx.shadowColor='rgba(110,225,255,.88)';
      ctx.strokeStyle=`rgba(${84+heat*46},${184+heat*31},${244+heat*8},.94)`;
      ctx.lineWidth=7+heat*3.2;ctx.beginPath();ctx.arc(0,0,s0*.54,0,Math.PI*2);ctx.stroke();
      ctx.shadowBlur=0;

      // V12 fallback scan arc (mirrors the WebGL spectral sweep).
      ctx.save();
      ctx.rotate(t*.72);
      const scanGrad=ctx.createLinearGradient(-s0,0,s0,0);
      scanGrad.addColorStop(0,'rgba(80,170,255,0)');
      scanGrad.addColorStop(.48,'rgba(130,220,255,.08)');
      scanGrad.addColorStop(.52,'rgba(210,245,255,.68)');
      scanGrad.addColorStop(.58,'rgba(85,180,255,.10)');
      scanGrad.addColorStop(1,'rgba(80,170,255,0)');
      ctx.strokeStyle=scanGrad;ctx.lineWidth=2.5+interaction*2;
      ctx.beginPath();ctx.arc(0,0,s0*.93,-.52,.52);ctx.stroke();
      ctx.restore();

      pts.forEach((p,i)=>{
        const a=p.a+t*(.05+(i%7)*.006);
        const rr=s0*(1.0+p.rr*1.95);
        const x=Math.cos(a)*rr,y=Math.sin(a)*rr*.82;
        ctx.fillStyle=i%6===0?'rgba(76,206,255,.94)':'rgba(176,208,236,.74)';
        ctx.beginPath();ctx.arc(x,y,p.r*(1+heat*.35),0,Math.PI*2);ctx.fill();
      });

      ctx.restore();
      requestAnimationFrame(draw);
    };
    requestAnimationFrame(draw);
    return true;
  };

  function expandCanvasForHubDive() {
    const rect = canvas.getBoundingClientRect();
    if (rect.width < 2 || rect.height < 2) return;
    const parentRect = (canvas.offsetParent || canvas.parentElement)?.getBoundingClientRect?.() || { left: 0 };
    const cx = rect.left + rect.width * 0.5;
    const safety = Math.max(48, innerWidth * 0.04);
    const half = Math.max(rect.width * 0.5, cx + safety, innerWidth - cx + safety);
    canvas.style.left = `${cx - half - parentRect.left}px`;
    canvas.style.width = `${half * 2}px`;
  }

  const api = window.__LoginGlbViewer__ = {
    ready: false,
    readyAt: 0,
    entering: false,
    enteredAt: 0,
    pointerX: 0,
    pointerY: 0,
    pointerClientX: 0,
    pointerClientY: 0,
    pointerSeen: false,
    pointerType: 'mouse',
    pointerActive: false,
    interaction: 0,
    enterHub() {
      expandCanvasForHubDive();
      api.entering = true;
      api.enteredAt = performance.now();
      api.interaction = 0;
    }
  };

  if (!gl) {
    if (startCanvas2DFallback()) return;
    setError('WEBGL UNAVAILABLE');
    return;
  }

  const vaoExt = !isWebGL2 ? gl.getExtension('OES_vertex_array_object') : null;
  const uintExt = !isWebGL2 ? gl.getExtension('OES_element_index_uint') : true;
  const createVAO = () => isWebGL2 ? gl.createVertexArray() : (vaoExt ? vaoExt.createVertexArrayOES() : null);
  const bindVAO = (vao) => {
    if (isWebGL2) gl.bindVertexArray(vao);
    else if (vaoExt) vaoExt.bindVertexArrayOES(vao);
  };

  try {
    const shaderSourceForContext = (type, src) => {
      if (isWebGL2) return src;
      let out = src.replace(/^\s*#version\s+300\s+es\s*/m, '');
      if (type === gl.VERTEX_SHADER) {
        out = out.replace(/layout\s*\(\s*location\s*=\s*\d+\s*\)\s*in\s+/g, 'attribute ');
        out = out.replace(/\bout\s+(?=(?:float|vec[234]|mat[234]|int|bool)\b)/g, 'varying ');
      } else {
        out = out.replace(/\bin\s+(?=(?:float|vec[234]|mat[234]|int|bool)\b)/g, 'varying ');
        out = out.replace(/\bout\s+vec4\s+C\s*;/g, '');
        out = out.replace(/\bC\s*=/g, 'gl_FragColor =');
        out = out.replace(/precision\s+highp\s+float\s*;/g, 'precision mediump float;');
      }
      return out;
    };

    const compile = (type, src) => {
      const shader = gl.createShader(type);
      gl.shaderSource(shader, shaderSourceForContext(type, src));
      gl.compileShader(shader);
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
        const log = gl.getShaderInfoLog(shader) || 'shader compile failed';
        gl.deleteShader(shader);
        throw new Error(log);
      }
      return shader;
    };

    const link = (vsSrc, fsSrc) => {
      const program = gl.createProgram();
      const vs = compile(gl.VERTEX_SHADER, vsSrc);
      const fs = compile(gl.FRAGMENT_SHADER, fsSrc);
      gl.attachShader(program, vs);
      gl.attachShader(program, fs);
      gl.linkProgram(program);
      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
        const log = gl.getProgramInfoLog(program) || 'program link failed';
        gl.deleteProgram(program);
        throw new Error(log);
      }
      return program;
    };

    const meshVS = `#version 300 es
    precision highp float;
    layout(location=0) in vec3 p;
    layout(location=1) in vec3 n;
    uniform mat4 P,V,M;
    out vec3 N,W;
    void main(){
      vec4 w=M*vec4(p,1.);
      W=w.xyz;
      N=normalize(mat3(M)*n);
      gl_Position=P*V*w;
    }`;

    const meshFS = `#version 300 es
    precision highp float;
    in vec3 N,W;
    uniform vec4 base;
    uniform float metal,rough,overheat,charge,burst,time,interaction,roleKind;
    uniform vec2 cursor;
    uniform vec3 emit;
    out vec4 C;

    const float PI=3.14159265359;

    float saturate(float x){return clamp(x,0.,1.);}
    vec3 fresnelSchlick(float cosTheta, vec3 F0){
      return F0 + (1.0 - F0) * pow(1.0 - cosTheta, 5.0);
    }
    vec3 fresnelSchlickRoughness(float cosTheta, vec3 F0, float roughness){
      return F0 + (max(vec3(1.0 - roughness), F0) - F0) * pow(1.0 - cosTheta, 5.0);
    }
    float DistributionGGX(vec3 N, vec3 H, float roughness){
      float a=roughness*roughness;
      float a2=a*a;
      float NdotH=max(dot(N,H),0.0);
      float NdotH2=NdotH*NdotH;
      float nom=a2;
      float denom=(NdotH2*(a2-1.0)+1.0);
      denom=PI*denom*denom;
      return nom/max(denom,0.0001);
    }
    float GeometrySchlickGGX(float NdotV, float roughness){
      float r=(roughness+1.0);
      float k=(r*r)/8.0;
      float nom=NdotV;
      float denom=NdotV*(1.0-k)+k;
      return nom/max(denom,0.0001);
    }
    float GeometrySmith(vec3 N, vec3 V, vec3 L, float roughness){
      float NdotV=max(dot(N,V),0.0);
      float NdotL=max(dot(N,L),0.0);
      float ggx2=GeometrySchlickGGX(NdotV,roughness);
      float ggx1=GeometrySchlickGGX(NdotL,roughness);
      return ggx1*ggx2;
    }
    vec3 envColor(vec3 dir){
      float up=saturate(dir.y*0.5+0.5);
      float horizon=exp(-pow(dir.y*6.5,2.0));
      vec3 sky=mix(vec3(.28,.50,.78),vec3(.68,.82,.96),up);
      vec3 floor=mix(vec3(.015,.030,.050),vec3(.11,.17,.24),saturate(-dir.y));
      vec3 band=vec3(.11,.24,.48)*horizon + vec3(.07,.20,.40)*pow(horizon,3.0);
      float sun=pow(max(dot(normalize(dir), normalize(vec3(-.28,.58,.76))),0.0), 420.0);
      vec3 sunCol=vec3(1.06,1.18,1.36)*sun;
      return mix(floor, sky+band, smoothstep(-.12,.22,dir.y)) + sunCol;
    }
    vec3 aces(vec3 x){
      const float a=2.51;
      const float b=0.03;
      const float c=2.43;
      const float d=0.59;
      const float e=0.14;
      return clamp((x*(a*x+b))/(x*(c*x+d)+e),0.,1.);
    }

    void main(){
      vec3 n=normalize(N);
      vec3 v=normalize(vec3(0.,0.,8.)-W);
      vec3 baseColor=base.rgb;
      float m=clamp(metal,0.,1.);
      float r=clamp(rough,0.04,1.);
      float heat=clamp(overheat,0.,1.);
      float ch=clamp(charge,0.,1.);
      float br=clamp(burst,0.,1.);

      vec3 F0=mix(vec3(0.04), baseColor, m);

      vec3 l1=normalize(vec3(-.45,.72,.85));
      vec3 l2=normalize(vec3(.52,.18,.62));
      vec3 l3=normalize(vec3(.12,-.82,.55));
      vec3 radiance1=vec3(1.10,1.30,1.62);
      vec3 radiance2=vec3(.30,.52,.98);
      vec3 radiance3=vec3(.07,.14,.28);

      vec3 Lo=vec3(0.0);
      for(int i=0;i<3;i++){
        vec3 L = i==0?l1:(i==1?l2:l3);
        vec3 radiance = i==0?radiance1:(i==1?radiance2:radiance3);
        vec3 H=normalize(v+L);
        float NDF=DistributionGGX(n,H,r);
        float G=GeometrySmith(n,v,L,r);
        vec3 F=fresnelSchlick(max(dot(H,v),0.0),F0);
        vec3 numerator=NDF*G*F;
        float denom=4.0*max(dot(n,v),0.0)*max(dot(n,L),0.0)+0.0001;
        vec3 specular=numerator/denom;
        vec3 kS=F;
        vec3 kD=(vec3(1.0)-kS)*(1.0-m);
        float NdotL=max(dot(n,L),0.0);
        Lo += (kD*baseColor/PI + specular)*radiance*NdotL;
      }

      vec3 R=reflect(-v,n);
      vec3 envDiff=envColor(n);
      vec3 envSpecSharp=envColor(R);
      vec3 envSpecSoft=envColor(normalize(mix(R,n,r*r)));
      vec3 envSpec=mix(envSpecSharp, envSpecSoft, saturate(r*1.15));
      vec3 F=fresnelSchlickRoughness(max(dot(n,v),0.0),F0,r);
      vec3 kS=F;
      vec3 kD=(vec3(1.0)-kS)*(1.0-m);
      vec3 ambient = kD * envDiff * baseColor * 0.34 + envSpec * (0.56 + 0.92 * (1.0-r)) * (0.45 + 0.55*m);

      float edge=pow(1.0-max(dot(n,v),0.0),2.9);
      float brushed = 1.0 + sin((W.x+W.y)*19.0 + W.z*12.0) * 0.055 * m * (1.0-r);
      vec3 metalSheen = vec3(.07,.12,.18) * edge * (0.55 + 0.70*m);

      vec3 et = normalize(max(emit, vec3(0.0001)));
      vec3 glowTint = mix(vec3(.50,.70,.94), et, .66);
      float aura = pow(1.0-max(dot(n,v),0.0),2.18)*(0.28 + heat*0.92 + ch*0.55 + br*1.25);
      vec3 hotWhite = vec3(.78,.88,.99);
      float hotSpec = heat*0.16 + ch*0.22 + br*0.58;
      float hotEdge = pow(1.0-max(dot(n,v),0.0),4.4) * (heat*0.28 + ch*0.36 + br*0.85);

      float angular = atan(W.y, W.x);
      float facetBand = .5 + .5 * sin(angular * 24.0 + length(W.xy) * 18.0);
      float cutline = smoothstep(.62, .98, facetBand) * (.05 + .10 * m) * (1.0 - r);
      vec3 color = (Lo + ambient) * brushed + metalSheen + vec3(.03,.05,.09) * cutline;
      color += emit * (0.82 + 0.85*heat + 0.62*ch + 1.35*br);
      color += glowTint * aura;
      color += hotWhite * (hotSpec + hotEdge);

      // V12 SpectralAegis: a narrow blue-white scan travels around the reactor,
      // inspired by the supplied spotlight/screen-blend visual language.
      float techMask=step(.5,roleKind);
      float coreMask=1.0-step(1.5,roleKind);
      float ringMask=step(1.5,roleKind);
      float sweepA=pow(max(cos(angular-time*(.52+interaction*.55)),0.0),32.0);
      float sweepB=pow(max(cos(angular+time*(.31+interaction*.36)+2.25),0.0),46.0);
      float radialPulse=.5+.5*sin(length(W.xy)*13.0-time*(1.35+interaction*1.10));
      float scan=(sweepA*.82+sweepB*.44)*(0.72+.28*radialPulse)*techMask;

      float cursorLen=length(cursor);
      vec2 cursorDir=cursor/max(cursorLen,.001);
      vec2 surfaceDir=W.xy/max(length(W.xy),.001);
      float cursorSpot=pow(max(dot(surfaceDir,vec2(cursorDir.x,-cursorDir.y)),0.0),18.0)
        * smoothstep(.08,.42,cursorLen)*interaction*techMask;

      float channelPulse=(.5+.5*sin(time*4.2+angular*12.0+length(W.xy)*9.0));
      float energyPulse=(.08+.15*interaction+.18*heat+.28*ch+.34*br);
      vec3 spectral=vec3(.12,.48,1.0)*(scan*(.13+.25*coreMask+.11*ringMask));
      spectral+=vec3(.42,.82,1.0)*cursorSpot*(.13+.24*coreMask+.12*ringMask);
      spectral+=vec3(.08,.34,.82)*channelPulse*energyPulse*emit.b*.055*techMask;
      color+=spectral;

      color = aces(color);
      color = pow(color, vec3(1.0/2.2));
      C = vec4(color, base.a);
    }`;

    const meshProgram = link(meshVS, meshFS);
    const MU = Object.fromEntries(['P','V','M','base','metal','rough','emit','overheat','charge','burst','time','interaction','roleKind','cursor'].map(k => [k, gl.getUniformLocation(meshProgram, k)]));

    const shellVS = `#version 300 es
    precision highp float;
    layout(location=0) in vec3 p;
    layout(location=1) in vec3 n;
    uniform mat4 P,V,M;
    out vec3 N,W;
    void main(){
      vec4 w=M*vec4(p,1.);
      W=w.xyz;
      N=normalize(mat3(M)*n);
      gl_Position=P*V*w;
    }`;

    const shellFS = `#version 300 es
    precision highp float;
    in vec3 N,W;
    uniform vec3 glowColor;
    uniform float intensity,time,roleKind;
    out vec4 C;
    void main(){
      vec3 n=normalize(N);
      vec3 v=normalize(vec3(0.,0.,8.)-W);
      float rim=pow(1.0-max(dot(n,v),0.0),2.25);
      float angular=atan(W.y,W.x);
      float pulse=.76+.24*sin(time*3.2+angular*6.0+length(W.xy)*5.0);
      float streak=.72+.28*pow(max(cos(angular-time*.85),0.0),12.0);
      float alpha=rim*(.12+.22*intensity)*pulse*streak;
      vec3 c=glowColor*(.62+1.45*rim)*intensity;
      C=vec4(c,alpha);
    }`;

    const shellProgram = link(shellVS, shellFS);
    const SU = Object.fromEntries(['P','V','M','glowColor','intensity','time','roleKind'].map(k => [k, gl.getUniformLocation(shellProgram, k)]));

    const particleVS = `#version 300 es
    precision highp float;
    layout(location=0) in vec3 p;
    layout(location=1) in float seed;
    layout(location=2) in float size;
    uniform mat4 P,V,M;
    uniform float time,interaction,reveal,overheat,burst;
    out float S,B,R,H;
    vec3 rx(vec3 q,float a){float c=cos(a),s=sin(a);return vec3(q.x,c*q.y-s*q.z,s*q.y+c*q.z);}
    vec3 ry(vec3 q,float a){float c=cos(a),s=sin(a);return vec3(c*q.x+s*q.z,q.y,-s*q.x+c*q.z);}
    vec3 rz(vec3 q,float a){float c=cos(a),s=sin(a);return vec3(c*q.x-s*q.y,s*q.x+c*q.y,q.z);}
    void main(){
      float dir=seed>.5?1.:-1.;
      vec3 q=p;
      q=rz(q,time*(.075+seed*.085)*dir);
      q=rx(q,time*(.026+fract(seed*7.91)*.047)*-dir);
      q=ry(q,time*(.019+fract(seed*13.17)*.041)*dir);
      q.z+=sin(time*1.05+seed*31.)*(.045+.07*interaction+.06*overheat+.10*burst);

      float coreMask=1.-smoothstep(1.35,2.35,length(p.xy));
      float life=fract(time*(.34+seed*.19+overheat*.08+burst*.22)+seed*13.73);
      float launch=smoothstep(.02,.10,life)*(1.-smoothstep(.78,1.,life));
      float travel=pow(life,.72);
      vec3 outDir=normalize(vec3(q.xy,q.z*.45+(seed-.5)*.35));
      float burstPush=interaction*coreMask*(.10+.78*travel+overheat*.18+burst*.72)*launch;
      q+=outDir*burstPush;
      q*=1.+interaction*(.010+.013*sin(time*.9+seed*17.))+overheat*.010+burst*.025;

      vec4 view=V*M*vec4(q,1.);
      gl_Position=P*view;
      B=interaction*coreMask*launch*.52 + burst*coreMask*(.34+travel*.46);
      R=reveal;
      S=seed;
      H=overheat+.55*burst;
      gl_PointSize=clamp((3.4+size*7.2+B*2.4+overheat*1.6+burst*3.2)*(9.4/max(1.,-view.z))*mix(.72,1.,reveal),2.2,34.);
    }`;

    const particleFS = `#version 300 es
    precision highp float;
    in float S,B,R,H;
    out vec4 C;
    void main(){
      float d=length(gl_PointCoord-.5)*2.;
      if(d>1.) discard;
      float soft=1.-smoothstep(.76,1.,d);
      float halo=exp(-d*d*2.55)*soft;
      float core=1.-smoothstep(.02,.23,d);
      float rim=exp(-pow((d-.56)*4.8,2.));
      float hot=smoothstep(.72,.98,fract(S*19.37));
      vec3 cyan=mix(vec3(.02,.42,.96),vec3(.28,.92,1.),fract(S*17.));
      vec3 white=vec3(.86,.98,1.);
      vec3 hotWhite=vec3(1.,.992,.982);
      vec3 col=cyan*(.70+halo*(1.10+.20*H))+white*(core*1.15+rim*(.72+hot*.72)+B*.52)+hotWhite*(H*.18*halo);
      float alpha=(.14+halo*.54+core*.46+rim*.22+B*.16+H*.06)*soft*R;
      C=vec4(col,alpha);
    }`;

    const particleProgram = link(particleVS, particleFS);
    const PU = Object.fromEntries(['P','V','M','time','interaction','reveal','overheat','burst'].map(k => [k, gl.getUniformLocation(particleProgram, k)]));

    const ventVS = `#version 300 es
    precision highp float;
    layout(location=0) in vec3 a;
    layout(location=1) in float size;
    uniform mat4 P,V,M;
    uniform float time,overheat,burst,reveal;
    out float A,F;
    vec3 rz(vec3 q,float ang){float c=cos(ang),s=sin(ang);return vec3(c*q.x-s*q.y,s*q.x+c*q.y,q.z);}
    void main(){
      float heat=smoothstep(.80,1.,overheat);
      float activation=max(heat*.55, burst);
      float seed=a.z;
      float life=fract(time*(1.3+seed*1.5+heat*2.2+burst*4.6)+seed*29.73);
      float gate=smoothstep(.0,.15,life)*(1.-smoothstep(.82,1.,life));
      float ang=a.x+seed*6.2831853+time*(1.4+seed*2.7+heat*2.1+burst*5.2);
      vec3 dir=normalize(vec3(cos(ang)*(0.95+.18*sin(seed*17.)),sin(ang)*(0.95+.18*cos(seed*19.)),a.y*.56+sin(seed*13.)*.22));
      float dist=(.12+.04*sin(seed*37.+time*4.))+pow(life,.58)*(.34+heat*2.2+seed*.75+burst*2.3);
      vec3 q=dir*dist;
      q=rz(q,time*(.9+heat*3.2+burst*5.0));
      q.z+=sin(time*7.0+seed*31.0)*(.05*heat+.12*burst);
      vec4 view=V*M*vec4(q,1.);
      gl_Position=P*view;
      A=activation*gate*reveal;
      F=life;
      gl_PointSize=clamp((4.4+size*9.4+heat*4.2+burst*9.0)*(10.2/max(1.,-view.z)),3.,48.);
    }`;

    const ventFS = `#version 300 es
    precision highp float;
    in float A,F;
    out vec4 C;
    void main(){
      float d=length(gl_PointCoord-.5)*2.;
      if(d>1.) discard;
      float soft=1.-smoothstep(.72,1.,d);
      float halo=exp(-d*d*2.25)*soft;
      float core=1.-smoothstep(.02,.20,d);
      float streak=exp(-pow((d-.44)*5.2,2.));
      vec3 white=vec3(1.,.994,.984);
      vec3 cool=vec3(.84,.97,1.);
      vec3 col=mix(cool,white,.78)*(halo*.94+core*1.24+streak*.48);
      float alpha=(.12+halo*.58+core*.44+streak*.18)*(1.-smoothstep(.85,1.,F))*A;
      C=vec4(col,alpha);
    }`;

    const ventProgram = link(ventVS, ventFS);
    const VU = Object.fromEntries(['P','V','M','time','overheat','burst','reveal'].map(k => [k, gl.getUniformLocation(ventProgram, k)]));

    const waveVS = `#version 300 es
    precision highp float;
    layout(location=0) in vec2 a;
    layout(location=1) in float seed;
    uniform mat4 P,V,M;
    uniform float time,overheat,burst,reveal;
    out float A,D;
    void main(){
      float activation=max(smoothstep(.86,1.,overheat)*.35, burst);
      float cycle=fract(time*(.44+activation*.22)+seed*.013);
      float ringGate=smoothstep(.0,.06,cycle)*(1.-smoothstep(.62,.92,cycle));
      float radius=.10+pow(cycle,.36)*(.85+burst*5.6+activation*1.4);
      float ang=a.x+time*(.18+burst*1.2)+seed*.04;
      vec3 q=vec3(cos(ang),sin(ang),sin(seed*1.7+time*3.1)*.04)*radius;
      vec4 view=V*M*vec4(q,1.);
      gl_Position=P*view;
      A=ringGate*reveal*activation;
      D=cycle;
      gl_PointSize=clamp((10.0+burst*34.0+activation*8.0)*(7.8/max(1.,-view.z)),4.,62.);
    }`;

    const waveFS = `#version 300 es
    precision highp float;
    in float A,D;
    out vec4 C;
    void main(){
      float d=length(gl_PointCoord-.5)*2.;
      if(d>1.) discard;
      float soft=1.-smoothstep(.74,1.,d);
      float halo=exp(-d*d*1.6)*soft;
      float ring=exp(-pow((d-.60)*6.0,2.))*1.25;
      vec3 white=vec3(1.,.993,.985);
      vec3 hot=vec3(1.,.97,.92);
      vec3 col=mix(white,hot,.35)*(halo*.32+ring);
      float alpha=(halo*.12+ring*.34)*(1.-smoothstep(.72,1.,D))*A;
      C=vec4(col,alpha);
    }`;

    const waveProgram = link(waveVS, waveFS);
    const WU = Object.fromEntries(['P','V','M','time','overheat','burst','reveal'].map(k => [k, gl.getUniformLocation(waveProgram, k)]));

    const hazeVS = `#version 300 es
    precision highp float;
    layout(location=0) in vec4 a;
    layout(location=1) in float size;
    uniform mat4 P,V,M;
    uniform float time,overheat,burst,reveal;
    out float A,T;
    void main(){
      float heat=smoothstep(.76,1.,overheat);
      float activation=heat + burst*.85;
      float seed=a.w;
      float ang=a.x + time*(.35+seed*.8+heat*1.9+burst*3.2) + sin(time*1.8+seed*31.)*.25;
      float rr=a.y*(1.+.08*sin(time*2.7+seed*21.));
      vec3 q=vec3(cos(ang)*rr,sin(ang)*rr,a.z);
      q.xy += vec2(sin(time*4.1+seed*11.),cos(time*3.7+seed*15.))* (0.03+0.07*heat+0.12*burst);
      q.z += sin(time*6.4+seed*17.)*(0.04+0.05*heat+0.10*burst);
      vec4 view=V*M*vec4(q,1.);
      gl_Position=P*view;
      A=activation*reveal;
      T=seed;
      gl_PointSize=clamp((18.+size*(8.+heat*12.+burst*18.))*(8.6/max(1.,-view.z)),6.,68.);
    }`;

    const hazeFS = `#version 300 es
    precision highp float;
    in float A,T;
    out vec4 C;
    void main(){
      float d=length(gl_PointCoord-.5)*2.;
      if(d>1.) discard;
      float soft=1.-smoothstep(.60,1.,d);
      float cloud=exp(-d*d*1.1)*soft;
      float swirl=.5+.5*sin(T*31.0+d*12.0);
      vec3 haze=mix(vec3(.88,.96,1.),vec3(1.,.985,.955),swirl*.45);
      float alpha=(.018+cloud*.095)*A;
      C=vec4(haze,alpha);
    }`;

    const hazeProgram = link(hazeVS, hazeFS);
    const HU = Object.fromEntries(['P','V','M','time','overheat','burst','reveal'].map(k => [k, gl.getUniformLocation(hazeProgram, k)]));

    const particleCount = 1120;
    const particleData = new Float32Array(particleCount * 5);
    let particleSeed = 0x21c0de;
    const rand = () => { particleSeed = (particleSeed * 1664525 + 1013904223) >>> 0; return particleSeed / 4294967296; };
    for (let i = 0; i < particleCount; i++) {
      const a = rand() * Math.PI * 2;
      const r = .82 + Math.pow(rand(), .68) * 2.78;
      const z = (rand() - .5) * (.36 + r * .28);
      const o = i * 5;
      const roll = rand();
      particleData[o] = Math.cos(a) * r;
      particleData[o + 1] = Math.sin(a) * r;
      particleData[o + 2] = z;
      particleData[o + 3] = rand();
      particleData[o + 4] = roll > .94 ? 1.8 + rand() * 1.3 : roll > .67 ? .9 + rand() * .8 : .28 + rand() * .62;
    }
    const particleVao = createVAO();
    bindVAO(particleVao);
    const particleBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, particleBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, particleData, gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 20, 0);
    gl.enableVertexAttribArray(1); gl.vertexAttribPointer(1, 1, gl.FLOAT, false, 20, 12);
    gl.enableVertexAttribArray(2); gl.vertexAttribPointer(2, 1, gl.FLOAT, false, 20, 16);
    bindVAO(null);

    const ventCount = 260;
    const ventData = new Float32Array(ventCount * 4);
    let ventSeed = 0x51eed;
    const vrand = () => { ventSeed = (ventSeed * 1664525 + 1013904223) >>> 0; return ventSeed / 4294967296; };
    for (let i = 0; i < ventCount; i++) {
      const o = i * 4;
      ventData[o] = vrand() * Math.PI * 2;
      ventData[o + 1] = (vrand() - .5) * 1.35;
      ventData[o + 2] = vrand();
      ventData[o + 3] = .35 + vrand() * 1.2;
    }
    const ventVao = createVAO();
    bindVAO(ventVao);
    const ventBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, ventBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, ventData, gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 16, 0);
    gl.enableVertexAttribArray(1); gl.vertexAttribPointer(1, 1, gl.FLOAT, false, 16, 12);
    bindVAO(null);

    const waveCount = 192;
    const waveData = new Float32Array(waveCount * 3);
    for (let i = 0; i < waveCount; i++) {
      const o = i * 3;
      waveData[o] = (i / waveCount) * Math.PI * 2;
      waveData[o + 1] = 0;
      waveData[o + 2] = i;
    }
    const waveVao = createVAO();
    bindVAO(waveVao);
    const waveBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, waveBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, waveData, gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 12, 0);
    gl.enableVertexAttribArray(1); gl.vertexAttribPointer(1, 1, gl.FLOAT, false, 12, 8);
    bindVAO(null);

    const hazeCount = 160;
    const hazeData = new Float32Array(hazeCount * 5);
    let hazeSeed = 0x7777aa;
    const hrand = () => { hazeSeed = (hazeSeed * 1664525 + 1013904223) >>> 0; return hazeSeed / 4294967296; };
    for (let i = 0; i < hazeCount; i++) {
      const o = i * 5;
      hazeData[o] = hrand() * Math.PI * 2;
      hazeData[o + 1] = .28 + hrand() * 1.18;
      hazeData[o + 2] = (hrand() - .5) * (.55 + hrand() * .8);
      hazeData[o + 3] = hrand();
      hazeData[o + 4] = .6 + hrand() * 1.6;
    }
    const hazeVao = createVAO();
    bindVAO(hazeVao);
    const hazeBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, hazeBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, hazeData, gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 4, gl.FLOAT, false, 20, 0);
    gl.enableVertexAttribArray(1); gl.vertexAttribPointer(1, 1, gl.FLOAT, false, 20, 16);
    bindVAO(null);

    const ident = () => new Float32Array([1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]);
    const mul = (a,b) => {
      const o = new Float32Array(16);
      for (let c=0;c<4;c++) for (let r=0;r<4;r++) {
        o[c*4+r] = a[r]*b[c*4] + a[4+r]*b[c*4+1] + a[8+r]*b[c*4+2] + a[12+r]*b[c*4+3];
      }
      return o;
    };
    const perspective = (f,a,n,z) => {
      const q = 1 / Math.tan(f / 2), o = new Float32Array(16);
      o[0] = q / a; o[5] = q; o[10] = (z + n) / (n - z); o[11] = -1; o[14] = 2 * z * n / (n - z);
      return o;
    };
    const translate = (x,y,z) => { const o = ident(); o[12] = x; o[13] = y; o[14] = z; return o; };
    const rotate = (x,y,z,s=1) => {
      const cx=Math.cos(x), sx=Math.sin(x), cy=Math.cos(y), sy=Math.sin(y), cz=Math.cos(z), sz=Math.sin(z);
      const o = ident();
      o[0]=s*cy*cz; o[1]=s*(sx*sy*cz+cx*sz); o[2]=s*(-cx*sy*cz+sx*sz);
      o[4]=s*(-cy*sz); o[5]=s*(-sx*sy*sz+cx*cz); o[6]=s*(cx*sy*sz+sx*cz);
      o[8]=s*sy; o[9]=-s*sx*cy; o[10]=s*cx*cy;
      return o;
    };
    const smooth = (t) => t*t*(3-2*t);

    let draws = [], mats = [], yaw = 0, pitch = 0, started = performance.now(), lastNow = started;
    let interaction = 0, ringBlend = 0, hoverHeat = 0, coinPhase = 0, trajectoryPhase = 0, energyPhase = 0, coreSpinPhase = 0;

    const accessor = (json, bin, i) => {
      const a = json.accessors[i], v = json.bufferViews[a.bufferView];
      const sizes = {5126:4,5125:4,5123:2};
      const ctors = {5126:Float32Array,5125:Uint32Array,5123:Uint16Array};
      const comps = {SCALAR:1,VEC2:2,VEC3:3,VEC4:4}[a.type];
      const stride = v.byteStride || comps * sizes[a.componentType];
      const offset = (v.byteOffset || 0) + (a.byteOffset || 0);
      const out = new ctors[a.componentType](a.count * comps);
      if (stride === comps * sizes[a.componentType]) {
        out.set(new ctors[a.componentType](bin, offset, a.count * comps));
      } else {
        const dv = new DataView(bin);
        for (let j=0;j<a.count;j++) for (let k=0;k<comps;k++) {
          const q = offset + j * stride + k * sizes[a.componentType];
          out[j*comps+k] = a.componentType===5126 ? dv.getFloat32(q,true) : a.componentType===5125 ? dv.getUint32(q,true) : dv.getUint16(q,true);
        }
      }
      return out;
    };

    fetch('/assets/login_mujoco_timeline.glb?v=2.16.11.6').then(r => {
      if (!r.ok) throw new Error(`GLB HTTP ${r.status}`);
      return r.arrayBuffer();
    }).then(buf => {
      const dv = new DataView(buf);
      const jsonLen = dv.getUint32(12, true);
      const json = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 20, jsonLen)));
      const binOffset = 20 + jsonLen + 8;
      const bin = buf.slice(binOffset);

      mats = json.materials.map(m => ({
        base: m.pbrMetallicRoughness?.baseColorFactor || [.5,.7,.8,1],
        metal: m.pbrMetallicRoughness?.metallicFactor || 0,
        rough: m.pbrMetallicRoughness?.roughnessFactor || .3,
        emit: m.emissiveFactor || [0,0,0]
      }));

      json.meshes[0].primitives.forEach(p => {
        const pos = accessor(json, bin, p.attributes.POSITION);
        const nor = accessor(json, bin, p.attributes.NORMAL);
        let idx = accessor(json, bin, p.indices);
        if (!isWebGL2 && idx instanceof Uint32Array && !uintExt) {
          let maxIndex = 0;
          for (let q=0;q<idx.length;q++) if (idx[q]>maxIndex) maxIndex=idx[q];
          if (maxIndex >= 65536) throw new Error('WEBGL1 INDEX LIMIT');
          idx = new Uint16Array(idx);
        }
        const vao = createVAO();
        bindVAO(vao);
        [[pos,0],[nor,1]].forEach(([data,loc]) => {
          const b = gl.createBuffer();
          gl.bindBuffer(gl.ARRAY_BUFFER, b);
          gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
          gl.enableVertexAttribArray(loc);
          gl.vertexAttribPointer(loc, 3, gl.FLOAT, false, 0, 0);
        });
        const ib = gl.createBuffer();
        gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, ib);
        gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, idx, gl.STATIC_DRAW);
        draws.push({
          vao,
          count: idx.length,
          type: idx instanceof Uint32Array ? gl.UNSIGNED_INT : gl.UNSIGNED_SHORT,
          material: p.material,
          role: p.extras?.role || 'legacy'
        });
      });

      api.ready = true;
      api.readyAt = performance.now();
      canvas.classList.add('is-ready');
      status?.classList.add('is-ready');
    }).catch(err => setError(err.message || '3D ASSET LOAD ERROR'));

    const updatePointer = e => {
      api.pointerType = e.pointerType || api.pointerType || 'mouse';
      if (api.pointerType === 'touch' && !api.pointerActive) return;
      api.pointerSeen = true;
      api.pointerClientX = e.clientX;
      api.pointerClientY = e.clientY;
      api.pointerX = (e.clientX / innerWidth - .5) * 2;
      api.pointerY = (e.clientY / innerHeight - .5) * 2;
    };
    addEventListener('pointermove', updatePointer, { passive: true });
    addEventListener('pointerdown', e => {
      api.pointerType = e.pointerType || 'mouse';
      if (api.pointerType !== 'mouse') api.pointerActive = true;
      updatePointer(e);
    }, { passive: true });
    const releasePointer = e => {
      if ((e?.pointerType || api.pointerType) !== 'mouse') {
        api.pointerActive = false;
        api.pointerSeen = false;
      }
    };
    addEventListener('pointerup', releasePointer, { passive: true });
    addEventListener('pointercancel', releasePointer, { passive: true });
    addEventListener('mouseout', e => { if (!e.relatedTarget && api.pointerType === 'mouse') api.pointerSeen = false; }, { passive: true });
    addEventListener('blur', () => { api.pointerSeen = false; api.pointerActive = false; }, { passive: true });

    const pointerInInteractionZone = () => {
      if (!api.pointerSeen || api.entering || reduceMotion) return false;
      const rect = canvas.getBoundingClientRect();
      if (rect.width < 8 || rect.height < 8) return false;
      const cx = rect.left + rect.width * .5, cy = rect.top + rect.height * .5;
      const radius = Math.max(92, Math.min(innerWidth, innerHeight, rect.height) * .255);
      const dx = (api.pointerClientX - cx) / radius, dy = (api.pointerClientY - cy) / (radius * .98);
      return dx*dx + dy*dy <= 1;
    };

    const ringMotion = (speedMul, maxTilt, phase, t, blend) => {
      const amt = maxTilt * blend * (.82 + .18 * Math.sin(t * (.44 * speedMul) + phase));
      const axis = phase + t * (.28 * speedMul) + .18 * Math.sin(t * (.11 * speedMul) + phase * 1.7);
      const axis2 = phase * .73 + t * (.21 * speedMul) + .16 * Math.cos(t * (.13 * speedMul) + phase * 1.1);
      const x = amt * Math.cos(axis);
      const y = amt * Math.sin(axis2);
      const z = .12 * blend * Math.sin(t * (.62 * speedMul) + phase * 1.9);
      return rotate(x, y, z);
    };

    function frame(now) {
      const loginScreen = canvas.closest('.login-screen');
      if (document.hidden || loginScreen?.classList.contains('hidden')) {
        lastNow = now;
        requestAnimationFrame(frame);
        return;
      }

      const dt = Math.min(.05, Math.max(0, (now - lastNow) * .001));
      lastNow = now;

      const hovering = pointerInInteractionZone();
      const target = hovering ? 1 : 0;
      const interactionRate = 1 - Math.exp(-dt / (target ? .10 : .30));
      interaction += (target - interaction) * interactionRate;
      if (Math.abs(target - interaction) < .001) interaction = target;
      api.interaction = interaction;

      const ringTarget = hovering ? 1 : 0;
      const ringRate = 1 - Math.exp(-dt / (ringTarget ? .28 : .42));
      ringBlend += (ringTarget - ringBlend) * ringRate;
      if (Math.abs(ringTarget - ringBlend) < .001) ringBlend = ringTarget;

      // V13 PrecisionFocus: hover reaches a composed activation plateau instead of
      // escalating into a repeated overheat/fireworks state on the login screen.
      hoverHeat = Math.min(.68, Math.max(0, hoverHeat + dt * (hovering ? .11 : -.30)));
      const heat = smooth(hoverHeat);
      const threshold = smooth(Math.max(0, heat - .90) / .10);
      const time = (now - started) * .001;
      const cycle = reduceMotion ? 0.0 : ((time * (.36 + threshold * .16)) % 1.0);
      const chargeLevel = threshold * (smooth(Math.min(1, cycle / .46)) * (1.0 - smooth(Math.max(0, (cycle - .52) / .20))));
      const burstLevel = threshold * (smooth(Math.max(0, (cycle - .68) / .12)) * (1.0 - smooth(Math.max(0, (cycle - .90) / .10))));
      const coreOverheat = Math.min(1, heat + threshold * 0.10 + burstLevel * .18);
      const particleHeat = smooth(Math.min(1, heat * 1.08));

      if (!reduceMotion) {
        coreSpinPhase += dt * (.055 + interaction * .20 + Math.pow(heat, 2.0) * .82 + burstLevel * 2.0);
        coinPhase += dt * (.040 + .22 * interaction + .07 * heat);
        trajectoryPhase += dt * (.014 + .085 * interaction + .045 * heat);
        energyPhase += dt * (.026 + .12 * interaction + .065 * heat);
      }

      const dpr = Math.min(devicePixelRatio || 1, 2);
      const w = Math.max(1, canvas.clientWidth * dpr | 0);
      const h = Math.max(1, canvas.clientHeight * dpr | 0);
      if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }

      gl.viewport(0, 0, w, h);
      gl.clearColor(0,0,0,0);
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      gl.enable(gl.DEPTH_TEST);
      gl.enable(gl.CULL_FACE);
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

      const yawTarget = reduceMotion ? 0 : api.pointerX * .13;
      const pitchTarget = reduceMotion ? 0 : -api.pointerY * .08;
      yaw += (yawTarget - yaw) * (1 - Math.exp(-dt / .28));
      pitch += (pitchTarget - pitch) * (1 - Math.exp(-dt / .28));

      const boot = reduceMotion || !api.readyAt ? 1 : smooth(Math.min(1, (now - api.readyAt) / 760));
      let scale = .94 + .06 * boot, cam = 9.4, spin = reduceMotion ? 0 : (now - started) * .000065;
      let enterT = 0;
      if (api.entering) {
        const enterDuration = reduceMotion ? 120 : 760;
        enterT = Math.min(1, (now - api.enteredAt) / enterDuration);
        if (reduceMotion) {
          canvas.style.opacity = String(1 - smooth(enterT));
        } else {
          const pre = smooth(Math.min(1, enterT / .26));
          const dive = smooth(Math.max(0, (enterT - .12) / .88));
          scale = (1 + .10 * pre) + 10.8 * Math.pow(dive, 1.58);
          cam = 9.4 - 2.45 * dive;
          spin += dive * .58;
          canvas.style.opacity = String(1 - smooth(Math.max(0, (enterT - .54) / .46)));
        }
      }

      const projection = perspective(Math.PI / 4, w / h, .03, 100);
      const view = translate(0, 0, -cam);
      const model = rotate(-.18 + pitch, .36 + yaw + spin, -.08, scale);
      const particleInteraction = Math.max(interaction, api.entering ? smooth(Math.min(1, enterT / .42)) : 0);

      const roleMatrix = (role) => {
        if (role === 'ring-c') return ringMotion(.90, .24, 1.2, time, ringBlend);
        if (role === 'ring-a') return ringMotion(1.35, .28, 0.35, time, ringBlend);
        if (role === 'ring-b') return ringMotion(1.80, .32, 2.1, time, ringBlend);
        if (role === 'core') {
          const compression = 1.0 - chargeLevel * .12 + burstLevel * .10;
          return rotate(.008*ringBlend*Math.sin(time*.82), .006*ringBlend*Math.cos(time*.71), coreSpinPhase, compression);
        }
        if (role === 'orbit-coin') return rotate(-.035*ringBlend*Math.sin(time*.61), .028*ringBlend*Math.cos(time*.77), -coinPhase);
        if (role === 'trajectory') return rotate(.018*ringBlend, -.024*ringBlend, trajectoryPhase);
        if (role === 'energy-baked') return rotate(.075*ringBlend*Math.sin(time*.43), .09*ringBlend*Math.cos(time*.39), energyPhase);
        return ident();
      };

      if (api.ready && draws.length) {
        gl.useProgram(meshProgram);
        gl.uniformMatrix4fv(MU.P, false, projection);
        gl.uniformMatrix4fv(MU.V, false, view);

        draws.forEach(draw => {
          const m = mats[draw.material];
          const local = roleMatrix(draw.role);
          const roleModel = mul(model, local);
          const isCore = draw.role === 'core';
          const isRing = draw.role === 'ring-a' || draw.role === 'ring-b' || draw.role === 'ring-c';
          const roleKind = isCore ? 1 : (isRing ? 2 : 0);

          let base = [m.base[0], m.base[1], m.base[2], m.base[3]];
          let metal = m.metal;
          let rough = m.rough;
          let emit = [m.emit[0], m.emit[1], m.emit[2]];
          let over = 0, charge = 0, burst = 0;

          if (isCore) {
            const silverMix = .07 * heat + .020 * chargeLevel;
            const azureBias = .22 + .15 * heat + .08 * interaction;
            base = [
              Math.min(1, base[0] * (1 + .015 * heat) * (1 - silverMix) + .66 * silverMix),
              Math.min(1, base[1] * (1 + .04 * heat) * (1 - silverMix) + .76 * silverMix + .07 * azureBias),
              Math.min(1, base[2] * (1 + .10 * heat) * (1 - silverMix) + .86 * silverMix + .20 * azureBias),
              base[3]
            ];
            metal = Math.min(1, m.metal + .035);
            rough = Math.max(.040, m.rough * (1 - heat * .07 - burstLevel * .07));
            emit = [
              emit[0] + .04 * heat + chargeLevel * .18 + burstLevel * .20,
              emit[1] + .26 * heat + chargeLevel * .40 + burstLevel * .70,
              emit[2] + .70 * heat + chargeLevel * .62 + burstLevel * 1.34
            ];
            over = coreOverheat;
            charge = chargeLevel;
            burst = burstLevel;
          } else if (isRing) {
            base = [
              Math.min(1, base[0] * .98 + .02 * interaction),
              Math.min(1, base[1] * 1.18 + .06 * interaction + .03 * heat),
              Math.min(1, base[2] * 1.32 + .11 * interaction + .07 * heat),
              base[3]
            ];
            emit = [
              emit[0] + .05 * interaction + .01 * heat,
              emit[1] + .18 * interaction + .06 * heat,
              emit[2] + .34 * interaction + .13 * heat
            ];
          }

          gl.uniformMatrix4fv(MU.M, false, roleModel);
          gl.uniform4fv(MU.base, base);
          gl.uniform1f(MU.metal, metal);
          gl.uniform1f(MU.rough, rough);
          gl.uniform3fv(MU.emit, emit);
          gl.uniform1f(MU.overheat, over);
          gl.uniform1f(MU.charge, charge);
          gl.uniform1f(MU.burst, burst);
          gl.uniform1f(MU.time, reduceMotion ? 0 : time);
          gl.uniform1f(MU.interaction, interaction);
          gl.uniform1f(MU.roleKind, roleKind);
          gl.uniform2f(MU.cursor, api.pointerX, api.pointerY);
          bindVAO(draw.vao);
          gl.drawElements(gl.TRIANGLES, draw.count, draw.type, 0);
        });

        gl.depthMask(false);
        gl.blendFunc(gl.SRC_ALPHA, gl.ONE);

        // V12 pseudo-bloom shell. This keeps the project dependency-free/offline
        // while giving the silver-blue core a soft screen/additive edge glow.
        gl.useProgram(shellProgram);
        gl.uniformMatrix4fv(SU.P, false, projection);
        gl.uniformMatrix4fv(SU.V, false, view);
        gl.uniform1f(SU.time, reduceMotion ? 0 : time);
        gl.cullFace(gl.FRONT);
        draws.forEach(draw => {
          const isCore = draw.role === 'core';
          const isRing = draw.role === 'ring-a' || draw.role === 'ring-b' || draw.role === 'ring-c';
          if (!isCore && !isRing) return;
          const local = roleMatrix(draw.role);
          const roleModel = mul(model, local);
          const glowScale = isCore ? (1.014 + heat*.006 + burstLevel*.010) : (1.010 + interaction*.004);
          const shellModel = mul(roleModel, rotate(0,0,0,glowScale));
          const intensity = isCore
            ? (.22 + interaction*.16 + heat*.24 + chargeLevel*.24 + burstLevel*.48)
            : (.11 + interaction*.18 + heat*.07);
          const glowColor = isCore ? [.20,.66,1.0] : [.12,.50,.96];
          gl.uniformMatrix4fv(SU.M, false, shellModel);
          gl.uniform3fv(SU.glowColor, glowColor);
          gl.uniform1f(SU.intensity, intensity);
          gl.uniform1f(SU.roleKind, isCore ? 1 : 2);
          bindVAO(draw.vao);
          gl.drawElements(gl.TRIANGLES, draw.count, draw.type, 0);
        });
        gl.cullFace(gl.BACK);

        gl.useProgram(hazeProgram);
        gl.uniformMatrix4fv(HU.P, false, projection);
        gl.uniformMatrix4fv(HU.V, false, view);
        gl.uniformMatrix4fv(HU.M, false, model);
        gl.uniform1f(HU.time, reduceMotion ? 0 : time);
        gl.uniform1f(HU.overheat, coreOverheat);
        gl.uniform1f(HU.burst, burstLevel);
        gl.uniform1f(HU.reveal, boot);
        bindVAO(hazeVao);
        gl.drawArrays(gl.POINTS, 0, hazeCount);

        gl.useProgram(particleProgram);
        gl.uniformMatrix4fv(PU.P, false, projection);
        gl.uniformMatrix4fv(PU.V, false, view);
        gl.uniformMatrix4fv(PU.M, false, model);
        gl.uniform1f(PU.time, reduceMotion ? 0 : time);
        gl.uniform1f(PU.interaction, particleInteraction);
        gl.uniform1f(PU.reveal, boot);
        gl.uniform1f(PU.overheat, particleHeat);
        gl.uniform1f(PU.burst, burstLevel);
        bindVAO(particleVao);
        gl.drawArrays(gl.POINTS, 0, particleCount);

        gl.useProgram(ventProgram);
        gl.uniformMatrix4fv(VU.P, false, projection);
        gl.uniformMatrix4fv(VU.V, false, view);
        gl.uniformMatrix4fv(VU.M, false, model);
        gl.uniform1f(VU.time, reduceMotion ? 0 : time);
        gl.uniform1f(VU.overheat, coreOverheat);
        gl.uniform1f(VU.burst, burstLevel);
        gl.uniform1f(VU.reveal, boot);
        bindVAO(ventVao);
        gl.drawArrays(gl.POINTS, 0, ventCount);

        gl.useProgram(waveProgram);
        gl.uniformMatrix4fv(WU.P, false, projection);
        gl.uniformMatrix4fv(WU.V, false, view);
        gl.uniformMatrix4fv(WU.M, false, model);
        gl.uniform1f(WU.time, reduceMotion ? 0 : time);
        gl.uniform1f(WU.overheat, coreOverheat);
        gl.uniform1f(WU.burst, burstLevel);
        gl.uniform1f(WU.reveal, boot);
        bindVAO(waveVao);
        gl.drawArrays(gl.POINTS, 0, waveCount);

        gl.depthMask(true);
        gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
      }

      requestAnimationFrame(frame);
    }

    requestAnimationFrame(frame);
  } catch (err) {
    setError(err.message || 'VIEWER INIT ERROR');
  }
})();