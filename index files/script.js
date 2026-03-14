// ════════════════════════════════════
// STATE
// ════════════════════════════════════
const state = {
  user: null,
  loggedIn: false
};

// Fake user pool for demo
const demoUsers = [
  {name:'Arjun Sharma',email:'arjun.sharma@gmail.com'},
  {name:'Rahul Verma',email:'rahul.verma@gmail.com'},
  {name:'Priya Singh',email:'priya.singh@gmail.com'},
];

// ════════════════════════════════════
// AUTH
// ════════════════════════════════════
function openLogin(){
  document.getElementById('loginOverlay').classList.add('open');
}

function closeLogin(){
  document.getElementById('loginOverlay').classList.remove('open');
}

function handleOverlayClick(e){
  if(e.target === document.getElementById('loginOverlay')) closeLogin();
}

function handleGoogleLogin(){
  const btn = document.getElementById('googleBtn');
  const txt = document.getElementById('googleBtnText');
  const spin = document.getElementById('loginSpinner');

  btn.disabled = true;
  txt.textContent = 'Authenticating...';
  spin.style.display = 'block';

  // Simulate OAuth flow
  setTimeout(()=>{
    const user = demoUsers[Math.floor(Math.random() * demoUsers.length)];
    state.user = user;
    state.loggedIn = true;

    // Update UI with user info
    const initials = user.name.split(' ').map(w=>w[0]).join('').toUpperCase();
    document.getElementById('userAvatar').textContent = initials;
    document.getElementById('userName').textContent = user.name;
    document.getElementById('userEmail').textContent = user.email;
    document.getElementById('welcomeMsg').textContent = `Welcome, ${user.name.split(' ')[0]} 👋`;
    document.getElementById('welcomeSub').textContent = `Signed in as ${user.email}`;

    // Reset button
    btn.disabled = false;
    txt.textContent = 'Continue with Google';
    spin.style.display = 'none';

    // Close modal, show dashboard
    closeLogin();
    showDashboard();
  }, 1800);
}

function handleLogout(){
  state.user = null;
  state.loggedIn = false;
  showLanding();
}

// ════════════════════════════════════
// PAGE ROUTING
// ════════════════════════════════════
function showLanding(){
  document.getElementById('landing').classList.add('active');
  document.getElementById('dashboard').classList.remove('active');
  document.getElementById('landing').style.display = '';
  document.getElementById('dashboard').style.display = 'none';
}

function showDashboard(){
  document.getElementById('landing').classList.remove('active');
  document.getElementById('dashboard').classList.add('active');
  document.getElementById('landing').style.display = 'none';
  document.getElementById('dashboard').style.display = 'flex';
  showView('home');
}

// Dashboard views
const views = ['home','scan','results','dorks','ai','reports'];

function showView(name){
  views.forEach(v=>{
    const el = document.getElementById('view-'+v);
    if(el) el.style.display = 'none';
  });
  const target = document.getElementById('view-'+name);
  if(target){ target.style.display = 'block'; }

  // Update nav active state
  document.querySelectorAll('.nav-link').forEach(link => link.classList.remove('active'));
}

// ════════════════════════════════════
// SCAN UI (demo — no real scan)
// ════════════════════════════════════
function startScan(){
  const target = document.getElementById('targetInput').value.trim();
  if(!target){
    const msg = document.getElementById('scanStatusMsg');
    msg.textContent = '⚠ Enter a target domain first.';
    msg.style.color = 'var(--danger)';
    return;
  }

  document.getElementById('progressCard').style.display = 'block';
  document.getElementById('startBtn').disabled = true;
  document.getElementById('scanStatusMsg').textContent = '';

  const steps = ['s1','s2','s3','s4','s5'];
  const pcts = [10,28,55,80,100];
  const logs = [
    `Initializing scan session for ${target}...`,
    `Generating dorks for selected categories...`,
    `Discovery phase — backend not connected yet`,
    `URL validation — scanner not connected yet`,
    `Scan flow complete. Connect backend for real results.`,
  ];

  const logEl = document.getElementById('scanLog');
  let i = 0;

  function next(){
    steps.forEach((s,idx)=>{
      const el = document.getElementById(s);
      el.className = 'step' + (idx < i ? ' done' : idx === i ? ' active' : '');
    });
    document.getElementById('progressFill').style.width = pcts[i]+'%';
    document.getElementById('pctLabel').textContent = pcts[i]+'%';

    const ts = new Date().toTimeString().split(' ')[0];
    const cls = i===4 ? 'log-ok' : 'log-info';
    logEl.innerHTML += `\n<span><span class="log-ts">${ts}</span><span class="${cls}">${logs[i]}</span></span>`;
    logEl.scrollTop = logEl.scrollHeight;

    i++;
    if(i < steps.length) setTimeout(next, 1100);
    else {
      setTimeout(()=>{
        steps.forEach(s=>{ document.getElementById(s).className='step done'; });
        document.getElementById('startBtn').disabled = false;
        document.getElementById('scanStatusMsg').textContent = 'Demo complete — connect backend for real scans.';
        document.getElementById('scanStatusMsg').style.color = 'var(--success)';
      }, 1100);
    }
  }
  setTimeout(next, 300);
}

function resetScan(){
  document.getElementById('targetInput').value = '';
  document.getElementById('progressCard').style.display = 'none';
  document.getElementById('scanStatusMsg').textContent = '';
  document.getElementById('startBtn').disabled = false;
  document.getElementById('progressFill').style.width = '0%';
  document.getElementById('pctLabel').textContent = '0%';
  ['s1','s2','s3','s4','s5'].forEach(s=>{ document.getElementById(s).className='step'; });
  document.getElementById('scanLog').innerHTML = '<span><span class="log-ts">00:00:00</span>Scanner ready. Waiting for input...</span>';
}

// Init
showLanding();
