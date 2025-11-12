// Trading Bot Dashboard JavaScript

class TradingBotDashboard {
    constructor() {
        this.ws = null;
        this.charts = {};
        this.updateInterval = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        
        this.init();
    }

    async init() {
        console.log('Initializing dashboard...');
        
        this.setupEventListeners();
        this.initializeCharts();
        await this.loadInitialData();
        this.setupWebSocket();
        this.startPeriodicUpdates();
    }

    setupEventListeners() {
        document.getElementById('start-btn').addEventListener('click', () => this.startBot());
        document.getElementById('stop-btn').addEventListener('click', () => this.stopBot());
        document.getElementById('emergency-btn').addEventListener('click', () => this.emergencyStop());
        document.getElementById('refresh-btn').addEventListener('click', () => this.refreshData());
    }

    async loadInitialData() {
        try {
            await Promise.all([
                this.updateStatus(),
                this.updatePositions(),
                this.updateOrders(),
                this.updatePerformance(),
                this.updateAccount()
            ]);
            
            this.updateLastUpdateTime();
        } catch (error) {
            console.error('Error loading initial data:', error);
            this.showError('Failed to load dashboard data');
        }
    }

    async updateStatus() {
        try {
            const response = await fetch('/api/status');
            const data = await response.json();
            
            const statusEl = document.getElementById('bot-status');
            const indicatorEl = document.getElementById('status-indicator');
            const textEl = document.getElementById('status-text');
            
            textEl.textContent = data.running ? 'Running' : 'Stopped';
            indicatorEl.className = `status-indicator ${data.running ? 'running' : 'stopped'}`;
            
            // Update system info
            document.getElementById('mode').textContent = data.mode.toUpperCase();
            document.getElementById('strategy').textContent = data.strategy;
            document.getElementById('symbols').textContent = data.symbols.join(', ');
            document.getElementById('uptime').textContent = this.formatUptime(data.uptime_seconds);
            
            // Update button states
            document.getElementById('start-btn').disabled = data.running;
            document.getElementById('stop-btn').disabled = !data.running;
            
        } catch (error) {
            console.error('Error updating status:', error);
        }
    }

    async updatePositions() {
        try {
            const response = await fetch('/api/positions');
            const positions = await response.json();
            
            const tbody = document.getElementById('positions-body');
            
            if (positions.length === 0) {
                tbody.innerHTML = '<tr class="no-data"><td colspan="6">No positions</td></tr>';
                return;
            }
            
            tbody.innerHTML = positions.map(pos => `
                <tr>
                    <td><strong>${pos.symbol}</strong></td>
                    <td>${pos.quantity.toFixed(2)}</td>
                    <td>$${pos.avg_price.toFixed(2)}</td>
                    <td>$${pos.current_price.toFixed(2)}</td>
                    <td class="${pos.unrealized_pnl >= 0 ? 'positive' : 'negative'}">
                        $${pos.unrealized_pnl.toFixed(2)}
                    </td>
                    <td class="${pos.unrealized_pnl_percent >= 0 ? 'positive' : 'negative'}">
                        ${pos.unrealized_pnl_percent.toFixed(2)}%
                    </td>
                </tr>
            `).join('');
            
        } catch (error) {
            console.error('Error updating positions:', error);
        }
    }

    async updateOrders() {
        try {
            const response = await fetch('/api/orders?limit=20');
            const orders = await response.json();
            
            const tbody = document.getElementById('orders-body');
            
            if (orders.length === 0) {
                tbody.innerHTML = '<tr class="no-data"><td colspan="7">No orders</td></tr>';
                return;
            }
            
            tbody.innerHTML = orders.map(order => `
                <tr>
                    <td>${new Date(order.timestamp).toLocaleTimeString()}</td>
                    <td><strong>${order.symbol}</strong></td>
                    <td>${order.side.toUpperCase()}</td>
                    <td>${order.order_type.toUpperCase()}</td>
                    <td>${order.quantity.toFixed(2)}</td>
                    <td>${order.price ? '$' + order.price.toFixed(2) : 'Market'}</td>
                    <td><span class="status-badge ${order.status.toLowerCase()}">${order.status}</span></td>
                </tr>
            `).join('');
            
        } catch (error) {
            console.error('Error updating orders:', error);
        }
    }

    async updatePerformance() {
        try {
            const response = await fetch('/api/performance');
            const data = await response.json();
            
            // Update metric cards
            this.updateMetricValue('daily-pnl', data.daily_pnl);
            this.updateMetricValue('total-pnl', data.total_pnl);
            this.updateMetricValue('equity', data.equity);
            
        } catch (error) {
            console.error('Error updating performance:', error);
        }
    }

    async updateAccount() {
        try {
            const response = await fetch('/api/account');
            const data = await response.json();
            
            this.updateMetricValue('balance', data.cash);
            
        } catch (error) {
            console.error('Error updating account:', error);
        }
    }

    updateMetricValue(elementId, value) {
        const element = document.getElementById(elementId);
        element.textContent = '$' + value.toFixed(2);
        
        // Add color class for P&L
        if (elementId.includes('pnl')) {
            element.className = 'metric-value ' + (value >= 0 ? 'positive' : 'negative');
        }
    }

    initializeCharts() {
        const ctx = document.getElementById('performance-chart').getContext('2d');
        
        this.charts.performance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Portfolio Value',
                    data: [],
                    borderColor: 'rgb(33, 150, 243)',
                    backgroundColor: 'rgba(33, 150, 243, 0.1)',
                    tension: 0.4,
                    fill: true
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        labels: {
                            color: '#c9d1d9'
                        }
                    }
                },
                scales: {
                    x: {
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)'
                        },
                        ticks: {
                            color: '#8b949e'
                        }
                    },
                    y: {
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)'
                        },
                        ticks: {
                            color: '#8b949e',
                            callback: function(value) {
                                return '$' + value.toLocaleString();
                            }
                        }
                    }
                }
            }
        });
    }

    setupWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/updates`;
        
        console.log('Connecting to WebSocket:', wsUrl);
        
        this.ws = new WebSocket(wsUrl);
        
        this.ws.onopen = () => {
            console.log('WebSocket connected');
            this.reconnectAttempts = 0;
        };
        
        this.ws.onmessage = (event) => {
            try {
                const message = JSON.parse(event.data);
                this.handleWebSocketMessage(message);
            } catch (error) {
                console.error('Error parsing WebSocket message:', error);
            }
        };
        
        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
        
        this.ws.onclose = () => {
            console.log('WebSocket closed, attempting to reconnect...');
            this.reconnectWebSocket();
        };
    }

    reconnectWebSocket() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('Max reconnection attempts reached');
            this.showError('Lost connection to server');
            return;
        }
        
        this.reconnectAttempts++;
        const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
        
        console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
        
        setTimeout(() => {
            this.setupWebSocket();
        }, delay);
    }

    handleWebSocketMessage(message) {
        console.log('WebSocket message:', message.type);
        
        switch (message.type) {
            case 'connected':
                console.log('WebSocket connection confirmed');
                break;
                
            case 'position_update':
                // Position updates are handled by periodic refresh
                break;
                
            case 'webhook_received':
                console.log('TradingView webhook received:', message.data);
                this.updateOrders();
                this.updatePositions();
                break;
                
            case 'emergency_stop':
                console.warn('Emergency stop executed');
                this.updateStatus();
                this.updatePositions();
                break;
                
            default:
                console.log('Unknown message type:', message.type);
        }
    }

    startPeriodicUpdates() {
        // Update data every 5 seconds
        this.updateInterval = setInterval(() => {
            this.updatePositions();
            this.updatePerformance();
            this.updateAccount();
            this.updateLastUpdateTime();
        }, 5000);
        
        // Update status less frequently
        setInterval(() => {
            this.updateStatus();
        }, 10000);
    }

    async startBot() {
        if (!confirm('Start the trading bot?')) {
            return;
        }
        
        try {
            const response = await fetch('/api/start', { method: 'POST' });
            const data = await response.json();
            
            if (response.ok) {
                console.log('Bot started:', data);
                await this.updateStatus();
                this.showSuccess('Bot started successfully');
            } else {
                throw new Error(data.detail || 'Failed to start bot');
            }
        } catch (error) {
            console.error('Error starting bot:', error);
            this.showError('Failed to start bot: ' + error.message);
        }
    }

    async stopBot() {
        if (!confirm('Stop the trading bot?')) {
            return;
        }
        
        try {
            const response = await fetch('/api/stop', { method: 'POST' });
            const data = await response.json();
            
            if (response.ok) {
                console.log('Bot stopped:', data);
                await this.updateStatus();
                this.showSuccess('Bot stopped successfully');
            } else {
                throw new Error(data.detail || 'Failed to stop bot');
            }
        } catch (error) {
            console.error('Error stopping bot:', error);
            this.showError('Failed to stop bot: ' + error.message);
        }
    }

    async emergencyStop() {
        if (!confirm('⚠️ EMERGENCY STOP - This will stop the bot and liquidate all positions. Are you sure?')) {
            return;
        }
        
        try {
            const response = await fetch('/api/emergency_stop', { method: 'POST' });
            const data = await response.json();
            
            if (response.ok) {
                console.warn('Emergency stop executed:', data);
                await this.updateStatus();
                await this.updatePositions();
                this.showSuccess(`Emergency stop executed. Liquidated ${data.liquidated_positions} positions.`);
            } else {
                throw new Error(data.detail || 'Failed to execute emergency stop');
            }
        } catch (error) {
            console.error('Error executing emergency stop:', error);
            this.showError('Failed to execute emergency stop: ' + error.message);
        }
    }

    async refreshData() {
        const btn = document.getElementById('refresh-btn');
        btn.disabled = true;
        btn.innerHTML = '<span class="loading"></span> Refreshing...';
        
        try {
            await this.loadInitialData();
            this.showSuccess('Data refreshed');
        } catch (error) {
            this.showError('Failed to refresh data');
        } finally {
            btn.disabled = false;
            btn.innerHTML = '🔄 Refresh';
        }
    }

    updateLastUpdateTime() {
        const now = new Date();
        document.getElementById('last-update').textContent = now.toLocaleTimeString();
    }

    formatUptime(seconds) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);
        
        if (hours > 0) {
            return `${hours}h ${minutes}m`;
        } else if (minutes > 0) {
            return `${minutes}m ${secs}s`;
        } else {
            return `${secs}s`;
        }
    }

    showSuccess(message) {
        console.log('Success:', message);
        // Could implement toast notifications here
    }

    showError(message) {
        console.error('Error:', message);
        alert(message);  // Simple alert for now
    }
}

// Initialize dashboard when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM loaded, initializing dashboard...');
    window.dashboard = new TradingBotDashboard();
});
