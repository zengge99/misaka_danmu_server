import { apiFetch } from '../api.js';

// DOM Elements
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
    if (targetSubView) targetSubView.classList.remove('hidden');

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

async function loadBangumiAuthState() {
    try {
        const state = await apiFetch('/api/bgm/auth/state');
        if (state.is_authenticated) {
            bangumiUserNickname.textContent = state.nickname;
            bangumiUserId.textContent = state.bangumi_user_id || 'N/A';
            bangumiAuthorizedAt.textContent = state.authorized_at ? new Date(state.authorized_at).toLocaleString() : 'N/A';
            bangumiExpiresAt.textContent = state.expires_at ? new Date(state.expires_at).toLocaleString() : '永不（或未知）';
            bangumiUserAvatar.src = state.avatar_url || '/static/placeholder.png';
            bangumiAuthStateAuthenticated.classList.remove('hidden');
            bangumiAuthStateUnauthenticated.classList.add('hidden');
        } else {
            bangumiAuthStateAuthenticated.classList.add('hidden');
            bangumiAuthStateUnauthenticated.classList.remove('hidden');
        }
    } catch (error) {
        bangumiAuthStateUnauthenticated.innerHTML = `<p class="error">获取授权状态失败: ${error.message}</p>`;
        bangumiAuthStateAuthenticated.classList.add('hidden');
        bangumiAuthStateUnauthenticated.classList.remove('hidden');
    }
}

async function handleBangumiLogin() {
    try {
        const { url } = await apiFetch('/api/bgm/auth/url');
        window.open(url, 'BangumiAuth', 'width=600,height=700');
    } catch (error) {
        alert(`启动 Bangumi 授权失败: ${error.message}`);
    }
}

async function handleBangumiLogout() {
    if (confirm("确定要注销 Bangumi 授权吗？")) {
        try {
            await apiFetch('/api/bgm/auth', { method: 'DELETE' });
            loadBangumiAuthState();
        } catch (error) {
            alert(`注销失败: ${error.message}`);
        }
    }
}

async function loadTmdbSettings() {
    tmdbSaveMessage.textContent = '';
    try {
        const data = await apiFetch('/api/ui/config/tmdb');
        document.getElementById('tmdb-api-key').value = data.tmdb_api_key || '';
        document.getElementById('tmdb-api-base-url').value = data.tmdb_api_base_url || '';
        document.getElementById('tmdb-image-base-url').value = data.tmdb_image_base_url || '';
    } catch (error) {
        tmdbSaveMessage.textContent = `加载TMDB配置失败: ${error.message}`;
    }
}

async function handleSaveTmdbSettings(e) {
    e.preventDefault();
    const payload = {
        tmdb_api_key: document.getElementById('tmdb-api-key').value.trim(),
        tmdb_api_base_url: document.getElementById('tmdb-api-base-url').value.trim(),
        tmdb_image_base_url: document.getElementById('tmdb-image-base-url').value.trim(),
    };
    const saveBtn = e.target.querySelector('button[type="submit"]');
    saveBtn.disabled = true;
    tmdbSaveMessage.textContent = '保存中...';
    tmdbSaveMessage.className = 'message';
    try {
        await apiFetch('/api/ui/config/tmdb', { method: 'PUT', body: JSON.stringify(payload) });
        tmdbSaveMessage.textContent = 'TMDB 配置保存成功！';
        tmdbSaveMessage.classList.add('success');
    } catch (error) {
        tmdbSaveMessage.textContent = `保存失败: ${error.message}`;
        tmdbSaveMessage.classList.add('error');
    } finally {
        saveBtn.disabled = false;
    }
}

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