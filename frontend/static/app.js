// Global state
let currentPage = 1;
let currentFilters = {};
let channelsChart = null;

// DOM elements
const elements = {
    totalMessages: document.getElementById('total-messages'),
    buySignals: document.getElementById('buy-signals'),
    holdSignals: document.getElementById('hold-signals'),
    recentActivity: document.getElementById('recent-activity'),
    avgConfidence: document.getElementById('avg-confidence'),
    recentBuySignals: document.getElementById('recent-buy-signals'),
    decisionFilter: document.getElementById('decision-filter'),
    channelFilter: document.getElementById('channel-filter'),
    confidenceFilter: document.getElementById('confidence-filter'),
    applyFilters: document.getElementById('apply-filters'),
    clearFilters: document.getElementById('clear-filters'),
    messagesBody: document.getElementById('messages-tbody'),
    paginationInfo: document.getElementById('pagination-info'),
    pageInfo: document.getElementById('page-info'),
    prevPage: document.getElementById('prev-page'),
    nextPage: document.getElementById('next-page')
};

// Initialize the dashboard
document.addEventListener('DOMContentLoaded', function() {
    loadStats();
    loadChannels();
    loadMessages();
    setupEventListeners();
    
    // Auto-refresh every 30 seconds
    setInterval(() => {
        loadStats();
        loadMessages();
    }, 30000);
});

// Setup event listeners
function setupEventListeners() {
    elements.applyFilters.addEventListener('click', applyFilters);
    elements.clearFilters.addEventListener('click', clearFilters);
    elements.prevPage.addEventListener('click', () => changePage(-1));
    elements.nextPage.addEventListener('click', () => changePage(1));
}

// Load dashboard statistics
async function loadStats() {
    try {
        const response = await fetch('/api/stats');
        const data = await response.json();
        
        if (response.ok) {
            updateStatsDisplay(data);
            updateRecentSignals(data.recent_buy_signals);
            updateChannelsChart(data.top_channels);
        } else {
            showError('Failed to load statistics');
        }
    } catch (error) {
        console.error('Error loading stats:', error);
        showError('Failed to load statistics');
    }
}

// Update statistics display
function updateStatsDisplay(data) {
    elements.totalMessages.textContent = data.total_messages.toLocaleString();
    elements.buySignals.textContent = data.buy_decisions.toLocaleString();
    elements.holdSignals.textContent = data.hold_decisions.toLocaleString();
    elements.recentActivity.textContent = data.recent_messages_24h.toLocaleString();
    elements.avgConfidence.textContent = (data.avg_confidence * 100).toFixed(1) + '%';
}

// Update recent buy signals
function updateRecentSignals(signals) {
    if (!signals || signals.length === 0) {
        elements.recentBuySignals.innerHTML = '<p class="no-signals">No recent high-confidence buy signals</p>';
        return;
    }
    
    elements.recentBuySignals.innerHTML = signals.map(signal => `
        <div class="signal-item">
            <div class="signal-header">
                <span class="signal-meta">
                    ${signal.channel_name} • ${signal.sender_name} • ${formatTime(signal.processed_at)}
                </span>
                <span class="signal-confidence">${(signal.confidence * 100).toFixed(0)}%</span>
            </div>
            <div class="signal-message">${escapeHtml(signal.message_text)}</div>
            ${signal.token_address ? `<div class="signal-token">Token: ${signal.token_address}</div>` : ''}
        </div>
    `).join('');
}

// Load channels for filter dropdown
async function loadChannels() {
    try {
        const response = await fetch('/api/channels');
        const channels = await response.json();
        
        if (response.ok) {
            elements.channelFilter.innerHTML = '<option value="">All Channels</option>' +
                channels.map(channel => `<option value="${escapeHtml(channel)}">${escapeHtml(channel)}</option>`).join('');
        }
    } catch (error) {
        console.error('Error loading channels:', error);
    }
}

// Load messages with current filters and pagination
async function loadMessages() {
    try {
        showLoading();
        
        const params = new URLSearchParams({
            page: currentPage,
            per_page: 20,
            ...currentFilters
        });
        
        const response = await fetch(`/api/messages?${params}`);
        const data = await response.json();
        
        if (response.ok) {
            updateMessagesTable(data.messages);
            updatePagination(data.pagination);
        } else {
            showError('Failed to load messages');
        }
    } catch (error) {
        console.error('Error loading messages:', error);
        showError('Failed to load messages');
    }
}

// Update messages table
function updateMessagesTable(messages) {
    if (!messages || messages.length === 0) {
        elements.messagesBody.innerHTML = '<tr><td colspan="7" class="no-data">No messages found</td></tr>';
        return;
    }
    
    elements.messagesBody.innerHTML = messages.map(message => `
        <tr>
            <td title="${formatFullTime(message.processed_at)}">${formatTime(message.processed_at)}</td>
            <td title="${escapeHtml(message.channel_name || 'Unknown')}">${escapeHtml(truncate(message.channel_name || 'Unknown', 15))}</td>
            <td title="${escapeHtml(message.sender_name || 'Unknown')}">${escapeHtml(truncate(message.sender_name || 'Unknown', 12))}</td>
            <td class="message-text" title="${escapeHtml(message.message_text || '')}">${escapeHtml(truncate(message.message_text || '', 50))}</td>
            <td><span class="decision-${message.llm_decision || 'unknown'}">${(message.llm_decision || 'Unknown').toUpperCase()}</span></td>
            <td><span class="confidence-${getConfidenceLevel(message.llm_confidence)}">${formatConfidence(message.llm_confidence)}</span></td>
            <td>${message.token_address ? `<span class="token-address" title="${message.token_address}">${truncate(message.token_address, 12)}</span>` : '-'}</td>
        </tr>
    `).join('');
}

// Update pagination controls
function updatePagination(pagination) {
    elements.paginationInfo.textContent = 
        `Showing ${Math.min((pagination.page - 1) * pagination.per_page + 1, pagination.total)}-${Math.min(pagination.page * pagination.per_page, pagination.total)} of ${pagination.total}`;
    
    elements.pageInfo.textContent = `Page ${pagination.page} of ${pagination.pages}`;
    
    elements.prevPage.disabled = pagination.page <= 1;
    elements.nextPage.disabled = pagination.page >= pagination.pages;
}

// Update channels chart
function updateChannelsChart(channels) {
    const ctx = document.getElementById('channels-chart').getContext('2d');
    
    if (channelsChart) {
        channelsChart.destroy();
    }
    
    if (!channels || channels.length === 0) {
        return;
    }
    
    channelsChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: channels.map(ch => ch.name),
            datasets: [{
                data: channels.map(ch => ch.count),
                backgroundColor: [
                    '#FF6384',
                    '#36A2EB',
                    '#FFCE56',
                    '#4BC0C0',
                    '#9966FF',
                    '#FF9F40'
                ],
                borderWidth: 2,
                borderColor: '#fff'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percentage = ((context.raw / total) * 100).toFixed(1);
                            return `${context.label}: ${context.raw} (${percentage}%)`;
                        }
                    }
                }
            }
        }
    });
}

// Apply filters
function applyFilters() {
    currentFilters = {};
    
    if (elements.decisionFilter.value) {
        currentFilters.decision = elements.decisionFilter.value;
    }
    
    if (elements.channelFilter.value) {
        currentFilters.channel = elements.channelFilter.value;
    }
    
    if (elements.confidenceFilter.value) {
        currentFilters.min_confidence = parseFloat(elements.confidenceFilter.value);
    }
    
    currentPage = 1;
    loadMessages();
}

// Clear filters
function clearFilters() {
    elements.decisionFilter.value = '';
    elements.channelFilter.value = '';
    elements.confidenceFilter.value = '';
    
    currentFilters = {};
    currentPage = 1;
    loadMessages();
}

// Change page
function changePage(direction) {
    currentPage += direction;
    loadMessages();
}

// Utility functions
function formatTime(isoString) {
    if (!isoString) return 'Unknown';
    
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);
    
    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    
    return date.toLocaleDateString();
}

function formatFullTime(isoString) {
    if (!isoString) return 'Unknown';
    return new Date(isoString).toLocaleString();
}

function formatConfidence(confidence) {
    if (confidence === null || confidence === undefined) return 'N/A';
    return (confidence * 100).toFixed(0) + '%';
}

function getConfidenceLevel(confidence) {
    if (confidence === null || confidence === undefined) return 'unknown';
    if (confidence >= 0.7) return 'high';
    if (confidence >= 0.4) return 'medium';
    return 'low';
}

function truncate(str, maxLength) {
    if (!str || str.length <= maxLength) return str;
    return str.substring(0, maxLength) + '...';
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showLoading() {
    elements.messagesBody.innerHTML = '<tr><td colspan="7" class="loading">Loading messages...</td></tr>';
}

function showError(message) {
    elements.messagesBody.innerHTML = `<tr><td colspan="7" class="error">${message}</td></tr>`;
}