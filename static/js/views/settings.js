import { apiFetch } from '../api.js';

let settingsSubNav, settingsSubViews;
let passwordChangeMessage;
let bangumiAuthStateUnauthenticated, bangumiAuthStateAuthenticated, bangumiUserNickname, bangumiUserId, bangumiAuthorizedAt, bangumiExpiresAt, bangumiUserAvatar, bangumiLoginBtn, bangumiLogoutBtn;
let tmdbSettingsForm, tmdbSaveMessage;

function initializeElements() {
    settingsSubNav = document.querySelector('#settings-view .settings-sub-nav');
    settingsSubViews = document.querySelectorAll('#settings-view .settings-subview');
    passwordChangeMessage = document.getElementById('password-change-message');
    
    bangumiAuthStateUnauthenticated = document.getElementById('bangumi-auth-state-unauthenticated');
    bangumiAuthStateAuthenticated = document.getElementById('bangumi-auth-state-authenticated');
    bangumiUserNickname = document.getElementById('bangumi-user-nickname');
    bangumiUserId = document.getElementById('bangumi-user-id');
    bangumiAuthorizedAt = document.getElementById('bangumi-authorized-at');
    bangumiExpiresAt = document.getElementById('bangumi-expires-at');
    bangumiUserAvatar = document.getElementById('bangumi-user-avatar');
    bangumiLoginBtn = document.getElementById('bangumi-login-btn');
    bangumiLogoutBtn = document.getElementById('bangumi-logout-btn');

    tmdbSettingsForm = document.getElementById('tmdb-settings-form');
    tmdbSaveMessage = document.getElementById('tmdb-save-message');
}

function handleSettingsSubNav(e) {
    const subNavBtn = e.target.closest('.sub-nav-btn');
    if (!subNavBtn) return;

    const subViewId = subNavBtn.getAttribute('data-subview');
    if (!subViewId) return;

    settingsSubNav.querySelectorAll('.sub-nav-btn').forEach(btn => btn.classList.remove('active'));
    subNavBtn.classList.add('active');

    settingsSubViews.forEach(view => view.classList.add('hidden'));
    const targetSubView = document.getElementById(subViewId);
    if (targetSubView) {
        targetSubView.classList.remove('hidden');
    }

    if (subViewId === 'bangumi-settings-subview') loadBangumiAuthState();
    if (subViewId === 'tmdb-settings-subview') loadTmdbSettings();
}

async function handleChangePassword(e) {
    e.preventDefault();
    passwordChangeMessage.textContent = '';
    passwordChangeMessage.className = 'message';

    const oldPassword = document.getElementById('old-password').value;
    const newPassword = document.getElementById('new-password').value;
    const confirmPassword = document.getElementById('confirm-password').value;

    if (newPassword.length < 8) {
        passwordChangeMessage.textContent = '新密码至少需要8位。';
        passwordChangeMessage.classList.add('error');
        return;
    }
    if (newPassword !== confirmPassword) {
        passwordChangeMessage.textContent = '两次输入的新密码不一致。';
        passwordChangeMessage.classList.add('error');
        return;
    }

    try {
        await apiFetch('/api/ui/auth/users/me/password', {
            method: 'PUT',
            body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
        });
        passwordChangeMessage.textContent = '密码修改成功！';
        passwordChangeMessage.classList.add('success');
        e.target.reset();
    } catch (error) {
        passwordChangeMessage.textContent = `修改失败: ${(error.message || error)}`;
        passwordChangeMessage.classList.add('error');
    }
}

async function loadBangumiAuthState() { /* ... */ }
async function handleBangumiLogin() { /* ... */ }
async function handleBangumiLogout() { /* ... */ }
async function loadTmdbSettings() { /* ... */ }
async function handleSaveTmdbSettings(e) { /* ... */ }

export function setupSettingsEventListeners() {
    initializeElements();
    settingsSubNav.addEventListener('click', handleSettingsSubNav);
    document.getElementById('change-password-form').addEventListener('submit', handleChangePassword);
    bangumiLoginBtn.addEventListener('click', handleBangumiLogin);
    bangumiLogoutBtn.addEventListener('click', handleBangumiLogout);
    tmdbSettingsForm.addEventListener('submit', handleSaveTmdbSettings);
    window.addEventListener('message', (event) => {
        if (event.data === 'BANGUMI-OAUTH-COMPLETE') {
            loadBangumiAuthState();
        }
    });

    document.addEventListener('viewchange', (e) => {
        if (e.detail.viewId === 'settings-view') {
            const firstSubNavBtn = settingsSubNav.querySelector('.sub-nav-btn');
            if (firstSubNavBtn) firstSubNavBtn.click();
        }
    });
}
