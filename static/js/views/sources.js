import { apiFetch } from '../api.js';
import { switchView } from '../ui.js';

// DOM Elements
let sourcesList, saveSourcesBtn, toggleSourceBtn, moveSourceUpBtn, moveSourceDownBtn;

function initializeElements() {
    sourcesList = document.getElementById('sources-list');
    saveSourcesBtn = document.getElementById('save-sources-btn');
    toggleSourceBtn = document.getElementById('toggle-source-btn');
    moveSourceUpBtn = document.getElementById('move-source-up-btn');
    moveSourceDownBtn = document.getElementById('move-source-down-btn');
}

async function loadScraperSettings() {
    if (!sourcesList) return;
    sourcesList.innerHTML = '<li>加载中...</li>';
    try {
        const settings = await apiFetch('/api/ui/scrapers');
        renderScraperSettings(settings);
    } catch (error) {
        sourcesList.innerHTML = `<li class="error">加载失败: ${(error.message || error)}</li>`;
    }
}

function renderScraperSettings(settings) {
    sourcesList.innerHTML = '';
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
            sourcesList.querySelectorAll('li').forEach(item => item.classList.remove('selected'));
            li.classList.add('selected');
        });
        sourcesList.appendChild(li);
    });
}

async function handleSaveSources() {
    const settingsToSave = [];
    sourcesList.querySelectorAll('li').forEach((li, index) => {
        settingsToSave.push({
            provider_name: li.dataset.providerName,
            is_enabled: li.dataset.isEnabled === 'true',
            display_order: index + 1,
        });
    });

    try {
        saveSourcesBtn.disabled = true;
        saveSourcesBtn.textContent = '保存中...';
        await apiFetch('/api/ui/scrapers', {
            method: 'PUT',
            body: JSON.stringify(settingsToSave),
        });
        alert('搜索源设置已保存！');
        loadScraperSettings();
    } catch (error) {
        alert(`保存失败: ${(error.message || error)}`);
    } finally {
        saveSourcesBtn.disabled = false;
        saveSourcesBtn.textContent = '保存设置';
    }
}

function handleToggleSource() {
    const selected = sourcesList.querySelector('li.selected');
    if (!selected) return;
    const isEnabled = selected.dataset.isEnabled === 'true';
    selected.dataset.isEnabled = !isEnabled;
    selected.querySelector('.status-icon').textContent = !isEnabled ? '✅' : '❌';
}

function handleMoveSource(direction) {
    const selected = sourcesList.querySelector('li.selected');
    if (!selected) return;
    if (direction === 'up' && selected.previousElementSibling) {
        sourcesList.insertBefore(selected, selected.previousElementSibling);
    } else if (direction === 'down' && selected.nextElementSibling) {
        sourcesList.insertBefore(selected.nextElementSibling, selected);
    }
}

export function setupSourcesEventListeners() {
    initializeElements();
    saveSourcesBtn.addEventListener('click', handleSaveSources);
    toggleSourceBtn.addEventListener('click', handleToggleSource);
    moveSourceUpBtn.addEventListener('click', () => handleMoveSource('up'));
    moveSourceDownBtn.addEventListener('click', () => handleMoveSource('down'));

    document.addEventListener('viewchange', (e) => {
        if (e.detail.viewId === 'sources-view') {
            loadScraperSettings();
        }
    });
}