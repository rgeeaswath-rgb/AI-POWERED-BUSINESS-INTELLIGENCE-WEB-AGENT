document.addEventListener('DOMContentLoaded', () => {
    // Navigation
    const navDashboard = document.getElementById('nav-dashboard');
    const navChat = document.getElementById('nav-chat');
    const navWordcloud = document.getElementById('nav-wordcloud');
    const navRate = document.getElementById('nav-rate');
    const dashboardView = document.getElementById('dashboard-view');
    const chatView = document.getElementById('chat-view');
    const wordcloudView = document.getElementById('wordcloud-view');
    const rateView = document.getElementById('rate-view');

    function switchView(activeNav, activeView) {
        [navDashboard, navChat, navWordcloud, navRate].forEach(n => n.classList.remove('active'));
        [dashboardView, chatView, wordcloudView, rateView].forEach(v => v.classList.remove('active'));
        activeNav.classList.add('active');
        activeView.classList.add('active');
    }

    navDashboard.addEventListener('click', (e) => { e.preventDefault(); switchView(navDashboard, dashboardView); });
    navChat.addEventListener('click', (e) => { e.preventDefault(); switchView(navChat, chatView); });
    navWordcloud.addEventListener('click', (e) => { 
        e.preventDefault(); 
        switchView(navWordcloud, wordcloudView); 
        loadWordCloud();
    });
    navRate.addEventListener('click', (e) => { e.preventDefault(); switchView(navRate, rateView); });

    // Load KPIs
    fetch('/api/kpis')
        .then(res => res.json())
        .then(data => {
            document.getElementById('kpi-total').textContent = data.total_reviews;
            document.getElementById('kpi-rating').textContent = data.avg_rating;
            document.getElementById('kpi-sentiment').textContent = data.avg_sentiment;
            document.getElementById('kpi-positive').textContent = data.positive_percent + '%';
            document.getElementById('kpi-pos-bar').style.width = data.positive_percent + '%';
        });

    // Load Charts
    fetch('/api/charts')
        .then(res => res.json())
        .then(data => {
            initTrendChart(data.trend);
            initPieChart(data.pie);
            initRatingChart(data.ratings);
        });

    function initTrendChart(trend) {
        const ctx = document.getElementById('trendChart').getContext('2d');
        new Chart(ctx, {
            type: 'line',
            data: {
                labels: trend.labels,
                datasets: [{
                    label: 'Sentiment Score',
                    data: trend.data,
                    borderColor: '#38bdf8',
                    backgroundColor: 'rgba(56, 189, 248, 0.1)',
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                plugins: { legend: { display: false } },
                scales: {
                    y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#94a3b8' } },
                    x: { grid: { display: false }, ticks: { color: '#94a3b8' } }
                }
            }
        });
    }

    function initPieChart(pie) {
        const ctx = document.getElementById('pieChart').getContext('2d');
        new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: pie.labels,
                datasets: [{
                    data: pie.data,
                    backgroundColor: ['#22c55e', '#ef4444', '#94a3b8'],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: { position: 'bottom', labels: { color: '#94a3b8' } }
                }
            }
        });
    }

    function initRatingChart(ratings) {
        const ctx = document.getElementById('ratingChart').getContext('2d');
        new Chart(ctx, {
            type: 'bar',
            data: {
                labels: ratings.labels.map(l => l + ' Star'),
                datasets: [{
                    data: ratings.data,
                    backgroundColor: '#38bdf8',
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true,
                plugins: { legend: { display: false } },
                scales: {
                    y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#94a3b8' } },
                    x: { grid: { display: false }, ticks: { color: '#94a3b8' } }
                }
            }
        });
    }

    // Chatbot Logic
    const chatInput = document.getElementById('chat-input');
    const sendBtn = document.getElementById('send-btn');
    const chatMessages = document.getElementById('chat-messages');

    function appendMessage(sender, text) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${sender}`;
        
        // Improved markdown-like conversion
        const formattedText = text
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/^- (.*?)$/gm, '<li>$1</li>')
            .replace(/\n/g, '<br>');

        msgDiv.innerHTML = `
            <div class="message-content">${formattedText}</div>
            <div class="message-time">${new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</div>
        `;
        chatMessages.appendChild(msgDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function sendMessage() {
        const query = chatInput.value.trim();
        if (!query) return;

        appendMessage('user', query);
        chatInput.value = '';
        
        // Show typing indicator or just disable button
        sendBtn.disabled = true;
        chatInput.disabled = true;

        fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query })
        })
        .then(res => res.json())
        .then(data => {
            if (data.response) {
                appendMessage('bot', data.response);
            } else if (data.detail) {
                appendMessage('bot', 'Error: ' + JSON.stringify(data.detail));
            } else {
                appendMessage('bot', 'Sorry, I encountered an unexpected error.');
            }
        })
        .catch(err => {
            appendMessage('bot', 'Error connecting to the AI agent.');
            console.error(err);
        })
        .finally(() => {
            sendBtn.disabled = false;
            chatInput.disabled = false;
            chatInput.focus();
        });
    }

    sendBtn.addEventListener('click', sendMessage);
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });

    // Voice to Text
    const micBtn = document.getElementById('mic-btn');
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    
    if (SpeechRecognition) {
        const recognition = new SpeechRecognition();
        recognition.continuous = false;
        
        recognition.onstart = function() {
            micBtn.classList.add('recording');
        };
        
        recognition.onresult = function(event) {
            const transcript = event.results[0][0].transcript;
            chatInput.value = transcript;
        };
        
        recognition.onend = function() {
            micBtn.classList.remove('recording');
            // Wait for a tiny delay to ensure the UI is updated, then send full question
            setTimeout(() => {
                if (chatInput.value.trim() !== '') {
                    sendMessage();
                }
            }, 300);
        };
        
        micBtn.addEventListener('click', () => {
            recognition.start();
        });
    } else {
        micBtn.style.display = 'none';
    }

    // Export PDF
    const exportPdfBtn = document.getElementById('export-pdf-btn');
    exportPdfBtn.addEventListener('click', () => {
        window.print();
    });

    // Word Cloud Logic
    let wordCloudLoaded = false;
    function loadWordCloud() {
        if (wordCloudLoaded) return;
        
        const loading = document.getElementById('wordcloud-loading');
        const canvas = document.getElementById('wordcloud-canvas');
        
        fetch('/api/wordcloud')
            .then(res => res.json())
            .then(data => {
                if (!data.words || data.words.length === 0) {
                    loading.textContent = 'No data available for word cloud.';
                    loading.style.color = '#ef4444';
                    return;
                }
                
                loading.style.display = 'none';
                
                // Format data for wordcloud2.js: [[word, weight], ...]
                const maxCount = Math.max(...data.words.map(w => w.size));
                const minCount = Math.min(...data.words.map(w => w.size));
                
                const list = data.words.map(w => {
                    // Normalize weight between 15 and 80 for rendering
                    const weight = 15 + ((w.size - minCount) / (maxCount - minCount)) * 65;
                    return [w.text, weight];
                });
                
                const colors = ['#00f2fe', '#4facfe', '#38bdf8', '#818cf8', '#a78bfa', '#e879f9'];
                
                WordCloud(canvas, {
                    list: list,
                    fontFamily: 'Outfit, sans-serif',
                    weightFactor: 1,
                    classes: 'wordcloud-span-item',
                    color: function() {
                        return colors[Math.floor(Math.random() * colors.length)];
                    },
                    shape: 'circle',
                    backgroundColor: 'transparent',
                    rotateRatio: 0,
                    gridSize: 10
                });
                
                wordCloudLoaded = true;
            })
            .catch(err => {
                loading.textContent = 'Failed to load word cloud.';
                loading.style.color = '#ef4444';
                console.error(err);
            });
    }

    // Rate UI Logic
    let currentRating = 0;
    const stars = document.querySelectorAll('#star-rating span');
    const rateSubmitBtn = document.getElementById('rate-submit-btn');
    const rateComment = document.getElementById('rate-comment');
    const rateMessage = document.getElementById('rate-message');

    stars.forEach(star => {
        star.addEventListener('mouseover', function() {
            const val = this.getAttribute('data-value');
            stars.forEach(s => {
                if (s.getAttribute('data-value') <= val) s.classList.add('hovered');
                else s.classList.remove('hovered');
            });
        });

        star.addEventListener('mouseout', function() {
            stars.forEach(s => s.classList.remove('hovered'));
        });

        star.addEventListener('click', function() {
            currentRating = this.getAttribute('data-value');
            stars.forEach(s => {
                if (s.getAttribute('data-value') <= currentRating) s.classList.add('selected');
                else s.classList.remove('selected');
            });
        });
    });

    rateSubmitBtn.addEventListener('click', () => {
        if (currentRating === 0) {
            rateMessage.textContent = 'Please select a star rating first!';
            rateMessage.style.color = '#ef4444';
            rateMessage.style.display = 'block';
            return;
        }

        rateSubmitBtn.disabled = true;
        rateSubmitBtn.textContent = 'Submitting...';

        fetch('/api/rate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ rating: parseInt(currentRating), comment: rateComment.value })
        })
        .then(res => res.json())
        .then(data => {
            rateMessage.textContent = 'Thank you! Your feedback has been submitted successfully.';
            rateMessage.style.color = '#10b981';
            rateMessage.style.display = 'block';
            rateSubmitBtn.style.display = 'none';
        })
        .catch(err => {
            rateMessage.textContent = 'Error submitting feedback. Please try again.';
            rateMessage.style.color = '#ef4444';
            rateMessage.style.display = 'block';
            rateSubmitBtn.disabled = false;
            rateSubmitBtn.textContent = 'Submit Feedback';
        });
    });
});
