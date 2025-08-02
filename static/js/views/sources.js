import { apiFetch } from '../api.js';

// DOM Elements
let sourcesSubNav, sourcesSubViews;
let danmakuSourcesList, saveDanmakuSourcesBtn, toggleDanmakuSourceBtn, moveDanmakuSourceUpBtn, moveDanmakuSourceDownBtn;
let metadataSourcesList, saveMetadataSourcesBtn, moveMetadataSourceUpBtn, moveMetadataSourceDownBtn;

function initializeElements() {
    sourcesSubNav = document.querySelector('#sources-view .settings-sub-nav');
    sourcesSubViews = document.querySelectorAll('#sources-view .settings-subview');

    danmakuSourcesList = document.getElementById('danmaku-sources-list');
    saveDanmakuSourcesBtn = document.getElementById('save-danmaku-sources-btn');
    toggleDanmakuSourceBtn = document.getElementById('toggle-danmaku-source-btn');
    moveDanmakuSourceUpBtn = document.getElementById('move-danmaku-source-up-btn');
    moveDanmakuSourceDownBtn = document.getElementById('move-danmaku-source-down-btn');

    metadataSourcesList = document.getElementById('metadata-sources-list');
    saveMetadataSourcesBtn = document.getElementById('save-metadata-sources-btn');
    moveMetadataSourceUpBtn = document.getElementById('move-metadata-source-up-btn');
    moveMetadataSourceDownBtn = document.getElementById('move-metadata-source-down-btn');
}

function handleSourcesSubNav(e) {
    const subNavBtn = e.target.closest('.sub-nav-btn');
    if (!subNavBtn) return;

    const subViewId = subNavBtn.getAttribute('data-subview');
    if (!subViewId) return;

    sourcesSubNav.querySelectorAll('.sub-nav-btn').forEach(btn => btn.classList.remove('active'));
    subNavBtn.classList.add('active');

    sourcesSubViews.forEach(view => view.classList.add('hidden'));
    const targetSubView = document.getElementById(subViewId);
    if (targetSubView) targetSubView.classList.remove('hidden');

    if (subViewId === 'danmaku-sources-subview') loadDanmakuSources();
    if (subViewId === 'metadata-sources-subview') loadMetadataSources();
}

async function loadDanmakuSources() {
    if (!danmakuSourcesList) return;
    danmakuSourcesList.innerHTML = '<li>加载中...</li>';
    try {
        const settings = await apiFetch('/api/ui/scrapers');
        renderDanmakuSources(settings);
    } catch (error) {
        danmakuSourcesList.innerHTML = `<li class="error">加载失败: ${(error.message || error)}</li>`;
    }
}

function renderDanmakuSources(settings) {
    danmakuSourcesList.innerHTML = '';
    settings.forEach(setting => {
        const li = document.createElement('li');
        li.dataset.providerName = setting.provider_name;
        li.dataset.isEnabled = setting.is_enabled;
        li.textContent = setting.provider_name;
        const statusIcon = document.createElement('span');
        statusIcon.className = 'status-icon';
        statusIcon.textContent = setting.is_enabled ? '✅' : '❌';
        li.appendChild(statusIcon);
        li.addEventListener('click', () => {
            danmakuSourcesList.querySelectorAll('li').forEach(item => item.classList.remove('selected'));
            li.classList.add('selected');
        });
        danmakuSourcesList.appendChild(li);
    });
}

async function handleSaveDanmakuSources() {
    const settingsToSave = [];
    danmakuSourcesList.querySelectorAll('li').forEach((li, index) => {
        settingsToSave.push({
            provider_name: li.dataset.providerName,
            is_enabled: li.dataset.isEnabled === 'true',
            display_order: index + 1,
        });
    });
    try {
        saveDanmakuSourcesBtn.disabled = true;
        saveDanmakuSourcesBtn.textContent = '保存中...';
        await apiFetch('/api/ui/scrapers', {
            method: 'PUT',
            body: JSON.stringify(settingsToSave),
        });
        alert('搜索源设置已保存！');
        loadDanmakuSources();
    } catch (error) {
        alert(`保存失败: ${(error.message || error)}`);
    } finally {
        saveDanmakuSourcesBtn.disabled = false;
        saveDanmakuSourcesBtn.textContent = '保存设置';
    }
}

function handleToggleDanmakuSource() {
    const selected = danmakuSourcesList.querySelector('li.selected');
    if (!selected) return;
    const isEnabled = selected.dataset.isEnabled === 'true';
    selected.dataset.isEnabled = !isEnabled;
    selected.querySelector('.status-icon').textContent = !isEnabled ? '✅' : '❌';
}

function handleMoveDanmakuSource(direction) {
    const selected = danmakuSourcesList.querySelector('li.selected');
    if (!selected) return;
    if (direction === 'up' && selected.previousElementSibling) {
        danmakuSourcesList.insertBefore(selected, selected.previousElementSibling);
    } else if (direction === 'down' && selected.nextElementSibling) {
        danmakuSourcesList.insertBefore(selected.nextElementSibling, selected);
    }
}

async function loadMetadataSources() {
    if (!metadataSourcesList) return;
    metadataSourcesList.innerHTML = '<li>加载中...</li>';
    try {
        // This should be a new endpoint in the future, for now we hardcode it
        const sources = [
            { name: 'TMDB', status: '已配置' },
            { name: 'Bangumi', status: '已授权' }
        ];
        renderMetadataSources(sources);
    } catch (error) {
        metadataSourcesList.innerHTML = `<li class="error">加载失败: ${(error.message || error)}</li>`;
    }
}

function renderMetadataSources(sources) {
    metadataSourcesList.innerHTML = '';
    sources.forEach(source => {
        const li = document.createElement('li');
        li.dataset.sourceName = source.name;
        li.textContent = source.name;
        const statusIcon = document.createElement('span');
        statusIcon.className = 'status-icon';
        statusIcon.textContent = source.status;
        li.appendChild(statusIcon);
        li.addEventListener('click', () => {
            metadataSourcesList.querySelectorAll('li').forEach(item => item.classList.remove('selected'));
            li.classList.add('selected');
        });
        metadataSourcesList.appendChild(li);
    });
}

function handleMoveMetadataSource(direction) {
    const selected = metadataSourcesList.querySelector('li.selected');
    if (!selected) return;
    if (direction === 'up' && selected.previousElementSibling) {
        metadataSourcesList.insertBefore(selected, selected.previousElementSibling);
    } else if (direction === 'down' && selected.nextElementSibling) {
        metadataSourcesList.insertBefore(selected.nextElementSibling, selected);
    }
}

function handleSaveMetadataSources() {
    // In the future, this would save the order to the backend.
    alert('元信息搜索源的排序功能暂未实现后端保存。');
}

export function setupSourcesEventListeners() {
    initializeElements();
    sourcesSubNav.addEventListener('click', handleSourcesSubNav);

    saveDanmakuSourcesBtn.addEventListener('click', handleSaveDanmakuSources);
    toggleDanmakuSourceBtn.addEventListener('click', handleToggleDanmakuSource);
    moveDanmakuSourceUpBtn.addEventListener('click', () => handleMoveDanmakuSource('up'));
    moveDanmakuSourceDownBtn.addEventListener('click', () => handleMoveDanmakuSource('down'));

    saveMetadataSourcesBtn.addEventListener('click', handleSaveMetadataSources);
    moveMetadataSourceUpBtn.addEventListener('click', () => handleMoveMetadataSource('up'));
    moveMetadataSourceDownBtn.addEventListener('click', () => handleMoveMetadataSource('down'));

    document.addEventListener('viewchange', (e) => {
        if (e.detail.viewId === 'sources-view') {
            const firstSubNavBtn = sourcesSubNav.querySelector('.sub-nav-btn');
            if (firstSubNavBtn) firstSubNavBtn.click();
        }
    });
}