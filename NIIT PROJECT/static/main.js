const SERVER_URL = 'http://localhost:5000';

function createServerOfflineOverlay() {
  if (document.getElementById('serverOfflineOverlay')) return;

  const overlay = document.createElement('div');
  overlay.id = 'serverOfflineOverlay';
  overlay.style.cssText = `
    position: fixed;
    top: 0;
    left: 0;
    width: 100vw;
    height: 100vh;
    background: rgba(15, 23, 42, 0.96);
    backdrop-filter: blur(8px);
    z-index: 999999;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    color: #f8fafc;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    text-align: center;
    padding: 24px;
    box-sizing: border-box;
  `;

 

  document.body.appendChild(overlay);
}

function removeServerOfflineOverlay() {
  const overlay = document.getElementById('serverOfflineOverlay');
  if (overlay) overlay.remove();
}

function initTheme() {
  const savedTheme = localStorage.getItem('eirrs_theme') || 'dark';
  document.documentElement.setAttribute('data-theme', savedTheme);
  updateThemeIcon(savedTheme);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme');
  const nextTheme = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', nextTheme);
  localStorage.setItem('eirrs_theme', nextTheme);
  updateThemeIcon(nextTheme);
}

function updateThemeIcon(theme) {
  const icon = document.getElementById('themeIcon');
  if (icon) {
    icon.className = theme === 'dark' ? 'fa-solid fa-sun' : 'fa-solid fa-moon';
  }
}

function getActiveUser() {
  const userStr = localStorage.getItem('eirrs_user');
  return userStr ? JSON.parse(userStr) : null;
}

function handleLogout() {
  localStorage.removeItem('eirrs_user');
  window.location.href = `${SERVER_URL}/login.html`;
}

function updateLandingPageState() {
  const user = getActiveUser();
  const navActions = document.getElementById('navActions');
  const heroCta = document.getElementById('heroCta');

  if (user) {
    if (navActions) {
      navActions.innerHTML = `
        <button onclick="toggleTheme()" class="btn btn-outline btn-sm" style="border:none;" title="Toggle Theme">
          <i id="themeIcon" class="fa-solid fa-sun"></i>
        </button>
        <span style="color:var(--text-muted); font-size:0.85rem; margin-right:6px;">Hi, ${user.full_name.split(' ')[0]}</span>
        <a href="profile.html" class="btn btn-outline btn-sm"><i class="fa-solid fa-user"></i> Profile</a>
        <button onclick="handleLogout()" class="btn btn-outline btn-sm" title="Sign Out"><i class="fa-solid fa-arrow-right-from-bracket"></i></button>
      `;
    }
    if (heroCta) {
      heroCta.innerHTML = `
        <a href="report_incident.html" class="btn btn-danger btn-lg"><i class="fa-solid fa-bullhorn"></i> File Emergency</a>
        <a href="dashboard.html" class="btn btn-primary btn-lg"><i class="fa-solid fa-gauge"></i> Open Dashboard</a>
      `;
    }
  } else {
    if (navActions) {
      navActions.innerHTML = `
        <button onclick="toggleTheme()" class="btn btn-outline btn-sm" style="border:none;" title="Toggle Theme">
          <i id="themeIcon" class="fa-solid fa-sun"></i>
        </button>
        <a href="login.html" class="btn btn-outline btn-sm">Sign In</a>
        <a href="register.html" class="btn btn-primary btn-sm">Register</a>
      `;
    }
    if (heroCta) {
      heroCta.innerHTML = `
        <a href="login.html" class="btn btn-danger btn-lg">Sign In to Command Center</a>
      `;
    }
  }
  updateThemeIcon(document.documentElement.getAttribute('data-theme'));
}

function formatDate(dateStr) {
  if (!dateStr) return 'N/A';
  const d = new Date(dateStr);
  return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  updateLandingPageState();
});