import { apiFetch } from '../api.js';
import { switchView } from '../ui.js';

// DOM Elements
let tokenManagerView, tokenTableBody, addTokenBtn, addTokenView, addTokenForm;
let customDomainInput, saveDomainBtn, domainSaveMessage;

function initializeElements() {
    tokenManagerView = document.getElementById('token-manager-view');
    tokenTableBody = document.querySelector('#token-table tbody');
    addTokenBtn = document.getElementById('add-token-btn');
    addTokenView = document.getElementById('add-token-view');
    addTokenForm = document.getElementById('add-token-form');
    customDomainInput = document.getElementById('custom-domain-input');
    saveDomainBtn = document.getElementById('save-domain-btn');
    domainSaveMessage = document.getElementById('domain-save-message');
}

async function loadAndRenderTokens() {
    if (!tokenTableBody) return;
    tokenTableBody.innerHTML = '<tr><td colspan="5">加载中...</td></tr>';
    try {
        const tokens = await apiFetch('/api/ui/tokens');
        renderTokens(tokens);
    } catch (error) {
        tokenTableBody.innerHTML = `<tr class="error"><td colspan="5">加载失败: ${(error.message || error)}</td></tr>`;
    }
}

function renderTokens(tokens) {
    tokenTableBody.innerHTML = '';
    if (tokens.length === 0) {
        tokenTableBody.innerHTML = '<tr><td colspan="5">没有创建任何Token。</td></tr>';
        return;
    }

    tokens.forEach(token => {
        const row = tokenTableBody.insertRow();
        const enabledText = token.is_enabled ? '禁用' : '启用';
        row.innerHTML = `
            <td>${token.name}</td>
            <td><span class="token-value">${token.token}</span></td>
            <td class="token-status ${token.is_enabled ? '' : 'disabled'}">${token.is_enabled ? '✅' : '❌'}</td>
            <td>${new Date(token.created_at).toLocaleString()}</td>
            <td class="actions-cell">
                <div class="action-buttons-wrapper">
                    <button class="action-btn" data-action="copy" data-token-id="${token.id}" data-token-value="${token.token}" title="复制链接">📋</button>
                    <button class="action-btn" data-action="toggle" data-token-id="${token.id}" title="${enabledText}">${token.is_enabled ? '⏸️' : '▶️'}</button>
                    <button class="action-btn" data-action="delete" data-token-id="${token.id}" title="删除">🗑️</button>
                </div>
            </td>
        `;
    });
}

async function handleTokenAction(e) {
    const button = e.target.closest('.action-btn');
    if (!button) return;

    const action = button.dataset.action;
    const tokenId = parseInt(button.dataset.tokenId, 10);
    const tokenValue = button.dataset.tokenValue;

    if (action === 'copy') {
        const domain = customDomainInput.value.trim();
        const textToCopy = domain ? `${domain}/api/${tokenValue}` : tokenValue;
        navigator.clipboard.writeText(textToCopy).then(() => {
            alert(`已复制到剪贴板: ${textToCopy}`);
        }, (err) => {
            alert(`复制失败: ${err}。请手动复制。`);
        });
    } else if (action === 'toggle') {
        try {
            await apiFetch(`/api/ui/tokens/${tokenId}/toggle`, { method: 'PUT' });
            loadAndRenderTokens();
        } catch (error) {
            alert(`操作失败: ${error.message}`);
        }
    } else if (action === 'delete') {
        if (confirm("您确定要删除这个Token吗？此操作不可恢复。")) {
            try {
                await apiFetch(`/api/ui/tokens/${tokenId}`, { method: 'DELETE' });
                loadAndRenderTokens();
            } catch (error) {
                alert(`删除失败: ${error.message}`);
            }
        }
    }
}

async function handleAddTokenSave(e) {
    e.preventDefault();
    const nameInput = document.getElementById('add-token-name');
    const name = nameInput.value.trim();
    if (!name) {
        alert('名称不能为空。');
        return;
    }

    const saveButton = addTokenForm.querySelector('button[type="submit"]');
    saveButton.disabled = true;
    saveButton.textContent = '保存中...';

    try {
        await apiFetch('/api/ui/tokens', {
            method: 'POST',
            body: JSON.stringify({ name: name }),
        });
        document.getElementById('back-to-tokens-from-add-btn').click();
        loadAndRenderTokens();
    } catch (error) {
        alert(`添加失败: ${(error.message || error)}`);
    } finally {
        saveButton.disabled = false;
        saveButton.textContent = '保存';
    }
}

async function loadCustomDomain() {
    domainSaveMessage.textContent = '';
    domainSaveMessage.className = 'message';
    try {
        const data = await apiFetch('/api/ui/config/custom_api_domain');
        customDomainInput.value = data.value || '';
    } catch (error) {
        domainSaveMessage.textContent = `加载域名失败: ${(error.message || error)}`;
        domainSaveMessage.classList.add('error');
    }
}

async function handleSaveDomain() {
    const domain = customDomainInput.value.trim();
    const cleanedDomain = domain.endsWith('/') ? domain.slice(0, -1) : domain;
    
    domainSaveMessage.textContent = '';
    domainSaveMessage.className = 'message';
    saveDomainBtn.disabled = true;
    saveDomainBtn.textContent = '保存中...';

    try {
        await apiFetch('/api/ui/config/custom_api_domain', {
            method: 'PUT',
            body: JSON.stringify({ value: cleanedDomain })
        });
        domainSaveMessage.textContent = '域名保存成功！';
        domainSaveMessage.classList.add('success');
        customDomainInput.value = cleanedDomain;
    } catch (error) {
        domainSaveMessage.textContent = `保存失败: ${(error.message || error)}`;
        domainSaveMessage.classList.add('error');
    } finally {
        saveDomainBtn.disabled = false;
        saveDomainBtn.textContent = '保存域名';
    }
}

export function setupTokensEventListeners() {
    initializeElements();
    addTokenBtn.addEventListener('click', () => {
        switchView('add-token-view');
        addTokenForm.reset();
    });
    document.getElementById('back-to-tokens-from-add-btn').addEventListener('click', () => {
        switchView('token-manager-view');
    });
    addTokenForm.addEventListener('submit', handleAddTokenSave);
    saveDomainBtn.addEventListener('click', handleSaveDomain);
    tokenTableBody.addEventListener('click', handleTokenAction);

    document.addEventListener('viewchange', (e) => {
        if (e.detail.viewId === 'token-manager-view') {
            loadAndRenderTokens();
            loadCustomDomain();
        }
    });
}
