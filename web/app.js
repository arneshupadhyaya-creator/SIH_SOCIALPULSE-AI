/**
 * X Scraper & Audience Intelligence Studio — Client Logic
 */

document.addEventListener('DOMContentLoaded', () => {
  // Telemetry & Status Elements
  const poolStatusPill = document.getElementById('pool-status-pill');
  const poolStatusText = document.getElementById('pool-status-text');
  const cbStateBadge = document.getElementById('cb-state-badge');
  const cbFailRatio = document.getElementById('cb-fail-ratio');
  const cbProgressBar = document.getElementById('cb-progress-bar');
  const cbCooldownCaption = document.getElementById('cb-cooldown-caption');
  const accountsFileStatus = document.getElementById('accounts-file-status');
  const sessionCountBadge = document.getElementById('session-count-badge');
  const sessionEdgesCount = document.getElementById('session-edges-count');
  const lastLatencyVal = document.getElementById('last-latency-val');

  // Form Elements
  const scraperForm = document.getElementById('scraper-form');
  const queryInput = document.getElementById('query-input');
  const limitInput = document.getElementById('limit-input');
  const sinceInput = document.getElementById('since-input');
  const chkSentiment = document.getElementById('chk-sentiment');
  const chkDemographics = document.getElementById('chk-demographics');
  const chkTrends = document.getElementById('chk-trends');
  const chkNetwork = document.getElementById('chk-network');
  const btnRunScrape = document.getElementById('btn-run-scrape');
  const btnSpinner = document.getElementById('btn-spinner');
  const btnText = document.getElementById('btn-text');

  // Console Elements
  const consoleOutput = document.getElementById('console-output');
  const btnClearLogs = document.getElementById('btn-clear-logs');

  // Tab Panes & Badges
  const feedCount = document.getElementById('feed-count');
  const edgesCount = document.getElementById('edges-count');
  const feedEmptyState = document.getElementById('feed-empty-state');
  const tweetStream = document.getElementById('tweet-stream');

  const edgesEmptyState = document.getElementById('edges-empty-state');
  const edgesTableContainer = document.getElementById('edges-table-container');
  const edgesTableBody = document.getElementById('edges-table-body');

  // Sentiment Panes
  const sentimentEmptyState = document.getElementById('sentiment-empty-state');
  const sentimentDashboard = document.getElementById('sentiment-dashboard');
  const sentimentMixBars = document.getElementById('sentiment-mix-bars');
  const emotionMixList = document.getElementById('emotion-mix-list');
  const sarcasmBarFill = document.getElementById('sarcasm-bar-fill');
  const sarcasmVal = document.getElementById('sarcasm-val');
  const sentimentPerTweet = document.getElementById('sentiment-per-tweet');

  // Demographics Panes
  const demographicsEmptyState = document.getElementById('demographics-empty-state');
  const demographicsDashboard = document.getElementById('demographics-dashboard');
  const ageDist = document.getElementById('age-dist');
  const geoDist = document.getElementById('geo-dist');
  const langDist = document.getElementById('lang-dist');
  const profDist = document.getElementById('prof-dist');

  // Raw JSON
  const rawJsonViewer = document.getElementById('raw-json-viewer');
  const btnExportJson = document.getElementById('btn-export-json');

  // Accounts Modal
  const btnOpenAccounts = document.getElementById('btn-open-accounts');
  const accountsModal = document.getElementById('accounts-modal');
  const btnCloseModal = document.getElementById('btn-close-modal');
  const btnCancelModal = document.getElementById('btn-cancel-modal');
  const btnSaveAccounts = document.getElementById('btn-save-accounts');
  const accountsContentInput = document.getElementById('accounts-content-input');

  let currentScrapedData = null;

  // Logging helper
  function addLog(msg, type = 'info') {
    const entry = document.createElement('div');
    entry.className = `log-entry ${type}`;
    const now = new Date().toLocaleTimeString();
    entry.innerHTML = `<span class="log-time">[${now}]</span><span class="log-msg">${escapeHtml(msg)}</span>`;
    consoleOutput.appendChild(entry);
    consoleOutput.scrollTop = consoleOutput.scrollHeight;
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  // Clear logs
  btnClearLogs.addEventListener('click', () => {
    consoleOutput.innerHTML = '';
    addLog('Console cleared.');
  });

  // Prompt Preset Chips
  document.querySelectorAll('.preset-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const q = chip.getAttribute('data-query');
      if (q && queryInput) {
        queryInput.value = q;
        queryInput.focus();
        queryInput.parentElement.style.boxShadow = '0 0 0 2px var(--accent-indigo), 0 0 25px rgba(99, 102, 241, 0.4)';
        setTimeout(() => {
          queryInput.parentElement.style.boxShadow = '';
        }, 800);
      }
    });
  });

  // Fetch scraper status
  async function fetchStatus() {
    try {
      const res = await fetch('/api/scraper/status');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      // Accounts file
      if (data.accounts_file_exists) {
        accountsFileStatus.textContent = 'Active / Detected';
        accountsFileStatus.className = 'metric-val text-accent';
        poolStatusPill.querySelector('.status-dot').className = 'status-dot dot-green';
        poolStatusText.textContent = data.account_count ? `${data.account_count} Accounts Pool` : 'Pool Ready';
      } else {
        accountsFileStatus.textContent = 'Missing (accounts.txt)';
        accountsFileStatus.className = 'metric-val';
        accountsFileStatus.style.color = 'var(--accent-rose)';
        poolStatusPill.querySelector('.status-dot').className = 'status-dot dot-red';
        poolStatusText.textContent = 'No Accounts File';
      }

      // Circuit Breaker
      const cb = data.circuit_breaker;
      if (cb) {
        cbStateBadge.textContent = cb.state;
        if (cb.state === 'CLOSED') {
          cbStateBadge.className = 'badge badge-success';
        } else if (cb.state === 'HALF-OPEN') {
          cbStateBadge.className = 'badge badge-warning';
        } else {
          cbStateBadge.className = 'badge badge-danger';
        }

        cbFailRatio.textContent = `${cb.failure_count} / ${cb.threshold}`;
        const pct = Math.min(100, Math.round((cb.failure_count / cb.threshold) * 100));
        cbProgressBar.style.width = `${pct}%`;

        if (cb.state === 'OPEN') {
          cbCooldownCaption.textContent = `Breaker OPEN! Cooldown: ${Math.round(cb.remaining_cooldown)}s`;
          cbCooldownCaption.style.color = 'var(--accent-rose)';
        } else {
          cbCooldownCaption.textContent = 'Ready. Cooldown: 0s';
          cbCooldownCaption.style.color = 'var(--text-muted)';
        }
      }
    } catch (err) {
      console.warn('Status check error:', err);
      poolStatusText.textContent = 'Server Offline';
      poolStatusPill.querySelector('.status-dot').className = 'status-dot dot-yellow';
    }
  }

  // Initial status check & periodic poll
  fetchStatus();
  setInterval(fetchStatus, 8000);

  // Tabs
  const tabButtons = document.querySelectorAll('.tab-btn');
  tabButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      tabButtons.forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-pane').forEach(p => p.style.display = 'none');

      btn.classList.add('active');
      const targetId = btn.getAttribute('data-target');
      const targetPane = document.getElementById(targetId);
      if (targetPane) targetPane.style.display = 'block';
    });
  });

  // Run scraper + analysis execution
  scraperForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const query = queryInput.value.trim();
    const limit = parseInt(limitInput.value, 10) || 10;
    const since = sinceInput.value || null;

    if (!query) {
      alert('Please enter a search query or hashtag.');
      return;
    }

    const runFull = chkSentiment?.checked || chkDemographics?.checked || chkTrends?.checked || chkNetwork?.checked;
    const endpoint = runFull ? '/api/scraper/test-full' : '/api/scraper/test';

    btnRunScrape.disabled = true;
    btnSpinner.style.display = 'inline-block';
    btnText.textContent = runFull ? 'Running Full Intelligence Suite...' : 'Scraping live public X...';

    addLog(`Starting pipeline: query="${query}" limit=${limit} mode=${runFull ? 'Full 4-Engine Analytics' : 'Scrape Only'}`, 'info');
    const startTime = performance.now();

    try {
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, limit, since })
      });

      const latency = ((performance.now() - startTime) / 1000).toFixed(2);
      lastLatencyVal.textContent = `${latency}s`;

      const result = await res.json();

      if (!res.ok) {
        throw new Error(result.detail || `Request failed with HTTP ${res.status}`);
      }

      currentScrapedData = result;
      addLog(`Pipeline complete! Retrieved ${result.tweets.length} tweets in ${latency}s.`, 'success');

      // Update metrics
      sessionCountBadge.textContent = `${result.tweets.length} Items`;
      feedCount.textContent = result.tweets.length;
      edgesCount.textContent = (result.edges || []).length;
      sessionEdgesCount.textContent = `${(result.edges || []).length} Edges`;

      // Render feed
      renderTweetFeed(result.tweets);

      // Render edges
      renderEdges(result.edges || []);

      // Render Sentiment Intelligence
      if (result.sentiment_summary && Object.keys(result.sentiment_summary).length > 0) {
        renderSentiment(result.sentiment_summary, result.tweets);
        addLog(`Sentiment analyzed: ${result.sentiment_summary.total_analyzed} posts scored.`, 'info');
      }

      // Render Demographics Intelligence
      if (result.demographics_summary && result.demographics_summary.total_users > 0) {
        renderDemographics(result.demographics_summary);
        addLog(`Demographics inferred: ${result.demographics_summary.total_users} user profiles aggregated.`, 'info');
      }

      // Render Trends & Topics Intelligence
      if (result.trend_summary && Object.keys(result.trend_summary).length > 0) {
        renderTrends(result.trend_summary);
        addLog(`Trends detected: ${result.trend_summary.rising_trends.length} rising terms, ${result.trend_summary.topic_clusters.length} clusters.`, 'info');
      }

      // Render Network Topology & KOLs Intelligence
      if (result.network_summary && Object.keys(result.network_summary).length > 0) {
        renderNetwork(result.network_summary);
        addLog(`Network mapped: ${result.network_summary.total_nodes} nodes, ${result.network_summary.total_edges} edges, ${result.network_summary.influencers.length} KOLs identified.`, 'info');
      }

      // Raw JSON
      rawJsonViewer.textContent = JSON.stringify(result, null, 2);

      // Update status
      fetchStatus();
    } catch (err) {
      addLog(`Error: ${err.message}`, 'error');
      alert(`Scraper notice: ${err.message}`);
      fetchStatus();
    } finally {
      btnRunScrape.disabled = false;
      btnSpinner.style.display = 'none';
      btnText.textContent = 'Execute Intelligence Pipeline';
    }
  });

  // Render Tweet Feed
  function renderTweetFeed(tweets) {
    if (!tweets || tweets.length === 0) {
      feedEmptyState.style.display = 'flex';
      tweetStream.style.display = 'none';
      return;
    }

    feedEmptyState.style.display = 'none';
    tweetStream.style.display = 'flex';
    tweetStream.innerHTML = '';

    tweets.forEach(tweet => {
      const card = document.createElement('div');
      card.className = 'tweet-card';

      const user = tweet.user || {};
      const initials = (user.display_name || user.handle || 'X').substring(0, 2).toUpperCase();
      const verifiedIcon = user.verified ? '<span class="verified-check" title="Verified">✓</span>' : '';
      const dateStr = tweet.created_at ? new Date(tweet.created_at).toLocaleString() : '';

      // Sentiment badge
      let sentimentBadgeHtml = '';
      if (tweet.sentiment) {
        const sent = tweet.sentiment;
        const sentClass = `sentiment-${sent.label}`;
        const langTag = (sent.detected_language && sent.detected_language !== 'en') ? ` [${sent.detected_language.toUpperCase()}]` : '';
        sentimentBadgeHtml = `
          <span class="sentiment-badge ${sentClass}" title="Confidence: ${Math.round(sent.score * 100)}%">
            ${sent.label.toUpperCase()}${langTag} (${Math.round(sent.score * 100)}%) • ${sent.emotion}
          </span>
        `;
      }

      // Hashtags & Mentions pills
      let tagsHtml = '';
      if (tweet.hashtags && tweet.hashtags.length) {
        tagsHtml += tweet.hashtags.map(h => `<span class="tag-pill tag-hashtag">#${escapeHtml(h)}</span>`).join('');
      }
      if (tweet.mentions && tweet.mentions.length) {
        tagsHtml += tweet.mentions.map(m => `<span class="tag-pill tag-mention">@${escapeHtml(m)}</span>`).join('');
      }

      card.innerHTML = `
        <div class="tweet-header">
          <div class="tweet-author-info">
            <div class="avatar-placeholder">${initials}</div>
            <div class="author-names">
              <span class="author-display-name">${escapeHtml(user.display_name || user.handle || 'Anonymous')} ${verifiedIcon}</span>
              <span class="author-handle">@${escapeHtml(user.handle || 'user')} • ${user.followers_count ? user.followers_count.toLocaleString() + ' followers' : ''}</span>
            </div>
          </div>
          <div style="display: flex; flex-direction: column; align-items: flex-end; gap: 4px;">
            <span class="tweet-timestamp">${dateStr}</span>
            ${sentimentBadgeHtml}
          </div>
        </div>
        <div class="tweet-body">${escapeHtml(tweet.text)}</div>
        ${tweet.sentiment?.translated_text ? `
          <div class="tweet-translation">
            <span class="tweet-translation-tag">🌐 English Translation:</span>${escapeHtml(tweet.sentiment.translated_text)}
          </div>
        ` : ''}

        ${tagsHtml ? `<div class="tweet-tags">${tagsHtml}</div>` : ''}
        <div class="tweet-footer">
          <span class="tweet-stat" title="Likes">❤️ ${tweet.like_count || 0}</span>
          <span class="tweet-stat" title="Retweets">🔁 ${tweet.retweet_count || 0}</span>
          <span class="tweet-stat" title="Replies">💬 ${tweet.reply_count || 0}</span>
          <span class="tweet-stat" title="Quotes">📑 ${tweet.quote_count || 0}</span>
          <span class="tweet-stat" style="margin-left: auto; font-family: var(--font-mono); font-size: 0.7rem;">ID: ${tweet.post_id}</span>
        </div>
      `;

      tweetStream.appendChild(card);
    });
  }

  // Render Graph Edges
  function renderEdges(edges) {
    if (!edges || edges.length === 0) {
      edgesEmptyState.style.display = 'flex';
      edgesTableContainer.style.display = 'none';
      return;
    }

    edgesEmptyState.style.display = 'none';
    edgesTableContainer.style.display = 'block';
    edgesTableBody.innerHTML = '';

    edges.forEach(edge => {
      const tr = document.createElement('tr');
      const badgeClass = edge.edge_type === 'reply' ? 'badge-edge-reply' : 'badge-edge-quote';
      tr.innerHTML = `
        <td style="font-family: var(--font-mono);">${edge.source_user_id}</td>
        <td><span class="badge-edge ${badgeClass}">${edge.edge_type}</span></td>
        <td style="font-family: var(--font-mono);">${edge.target_user_id}</td>
        <td style="font-family: var(--font-mono); font-size: 0.75rem;">${edge.post_id}</td>
        <td style="font-size: 0.75rem;">${new Date(edge.created_at).toLocaleTimeString()}</td>
      `;
      edgesTableBody.appendChild(tr);
    });
  }

  // Render Sentiment Dashboard
  function renderSentiment(summary, tweets) {
    if (!summary || !summary.sentiment_mix) {
      sentimentEmptyState.style.display = 'flex';
      sentimentDashboard.style.display = 'none';
      return;
    }

    sentimentEmptyState.style.display = 'none';
    sentimentDashboard.style.display = 'block';

    // 1. Stacked Sentiment Mix Bars
    const mix = summary.sentiment_mix;
    const posPct = mix.positive?.percentage || 0;
    const negPct = mix.negative?.percentage || 0;
    const neuPct = mix.neutral?.percentage || 0;

    sentimentMixBars.innerHTML = `
      <div class="stacked-bar-row">
        <span class="stacked-bar-label">Positive</span>
        <div class="stacked-bar-track">
          <div class="stacked-bar-fill fill-positive" style="width: ${Math.max(posPct, 3)}%;">${posPct}%</div>
        </div>
      </div>
      <div class="stacked-bar-row">
        <span class="stacked-bar-label">Negative</span>
        <div class="stacked-bar-track">
          <div class="stacked-bar-fill fill-negative" style="width: ${Math.max(negPct, 3)}%;">${negPct}%</div>
        </div>
      </div>
      <div class="stacked-bar-row">
        <span class="stacked-bar-label">Neutral</span>
        <div class="stacked-bar-track">
          <div class="stacked-bar-fill fill-neutral" style="width: ${Math.max(neuPct, 3)}%;">${neuPct}%</div>
        </div>
      </div>
    `;

    // 2. Emotion Breakdown
    const emotions = summary.emotion_mix || {};
    let emoHtml = '';
    for (const [emo, data] of Object.entries(emotions)) {
      const fillClass = `fill-${emo.replace(/[^a-z0-9_-]/gi, '-')}`;
      emoHtml += `
        <div class="dist-row">
          <span class="dist-label">${escapeHtml(emo)}</span>
          <div class="dist-bar-track">
            <div class="dist-bar-fill ${fillClass}" style="width: ${Math.max(data.percentage, 3)}%;"></div>
          </div>
          <span class="dist-val">${data.percentage}% (${data.count})</span>
        </div>
      `;
    }
    emotionMixList.innerHTML = emoHtml || '<div class="sub-caption">No emotions detected</div>';

    // 3. Sarcasm Meter
    const sarcasmPct = Math.round((summary.avg_sarcasm_probability || 0) * 100);
    sarcasmBarFill.style.width = `${sarcasmPct}%`;
    sarcasmVal.textContent = `${sarcasmPct}%`;

    // 4. Per-Tweet Sentiment Stream
    sentimentPerTweet.innerHTML = '';
    const scoredTweets = (tweets || []).filter(t => t.sentiment);
    scoredTweets.slice(0, 8).forEach(tweet => {
      const card = document.createElement('div');
      card.className = 'tweet-card';
      const s = tweet.sentiment;
      const sentClass = `sentiment-${s.label}`;

      card.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
          <span style="font-weight: 600; font-size: 0.82rem; color: var(--text-primary);">
            @${escapeHtml(tweet.user?.handle || 'user')}
          </span>
          <div style="display: flex; gap: 8px;">
            <span class="sentiment-badge ${sentClass}">${s.label.toUpperCase()} (${Math.round(s.score * 100)}%)</span>
            <span class="tag-pill">${escapeHtml(s.emotion)}</span>
            <span class="tag-pill" style="color: var(--accent-amber);">Sarcasm: ${Math.round(s.sarcasm_prob * 100)}%</span>
          </div>
        </div>
        <div class="tweet-body" style="font-size: 0.84rem;">${escapeHtml(tweet.text)}</div>
        ${s.translated_text ? `
          <div class="tweet-translation">
            <span class="tweet-translation-tag">🌐 English Translation:</span>${escapeHtml(s.translated_text)}
          </div>
        ` : ''}
      `;
      sentimentPerTweet.appendChild(card);
    });

  }

  // Render Demographics Dashboard
  function renderDemographics(summary) {
    if (!summary || !summary.total_users || summary.total_users === 0) {
      demographicsEmptyState.style.display = 'flex';
      demographicsDashboard.style.display = 'none';
      return;
    }

    demographicsEmptyState.style.display = 'none';
    demographicsDashboard.style.display = 'block';

    function renderDist(container, distData) {
      if (!distData || Object.keys(distData).length === 0) {
        container.innerHTML = '<div class="sub-caption">No signal detected</div>';
        return;
      }
      let html = '';
      for (const [key, val] of Object.entries(distData)) {
        html += `
          <div class="dist-row">
            <span class="dist-label">${escapeHtml(key)}</span>
            <div class="dist-bar-track">
              <div class="dist-bar-fill" style="width: ${Math.max(val.percentage, 4)}%;"></div>
            </div>
            <span class="dist-val">${val.percentage}% (${val.count})</span>
          </div>
        `;
      }
      container.innerHTML = html;
    }

    renderDist(ageDist, summary.age_distribution);
    renderDist(geoDist, summary.geo_distribution);
    renderDist(langDist, summary.language_distribution);
    renderDist(profDist, summary.profession_distribution);
  }

  // ══════════════════════════════════════════════════════════════
  // RENDER TRENDS & TOPICS INTELLIGENCE
  // ══════════════════════════════════════════════════════════════
  function renderTrends(summary) {
    const trendsEmptyState = document.getElementById('trends-empty-state');
    const trendsDashboard = document.getElementById('trends-dashboard');
    const trendWindowVal = document.getElementById('trend-window-val');
    const trendTopTopicVal = document.getElementById('trend-top-topic-val');
    const trendClusterCountVal = document.getElementById('trend-cluster-count-val');
    const risingTrendsList = document.getElementById('rising-trends-list');
    const predictedViralList = document.getElementById('predicted-viral-list');
    const topicClustersGrid = document.getElementById('topic-clusters-grid');
    const discussionShiftsTimeline = document.getElementById('discussion-shifts-timeline');

    if (!summary || (!summary.rising_trends?.length && !summary.topic_clusters?.length)) {
      if (trendsEmptyState) trendsEmptyState.style.display = 'flex';
      if (trendsDashboard) trendsDashboard.style.display = 'none';
      return;
    }

    if (trendsEmptyState) trendsEmptyState.style.display = 'none';
    if (trendsDashboard) trendsDashboard.style.display = 'block';

    // Banner metrics
    if (trendWindowVal) trendWindowVal.textContent = `${summary.analyzed_window_hours || 1.0}h Window`;
    const topTopic = summary.rising_trends?.[0];
    if (trendTopTopicVal) trendTopTopicVal.textContent = topTopic ? topTopic.keyword : '--';
    if (trendClusterCountVal) trendClusterCountVal.textContent = `${summary.topic_clusters?.length || 0} Clusters`;

    // 1. Rising Trends List
    if (risingTrendsList) {
      risingTrendsList.innerHTML = '';
      (summary.rising_trends || []).forEach(t => {
        const row = document.createElement('div');
        row.className = 'trend-row';

        let velClass = 'velocity-steady';
        let velPrefix = '';
        if (t.growth_rate > 50) {
          velClass = 'velocity-explosive';
          velPrefix = '🔥 +';
        } else if (t.growth_rate > 0) {
          velClass = 'velocity-rising';
          velPrefix = '▲ +';
        } else if (t.growth_rate < -20) {
          velClass = 'velocity-fading';
          velPrefix = '▼ ';
        }

        const isHash = t.is_hashtag;
        row.innerHTML = `
          <div class="trend-term-box">
            <span class="trend-keyword ${isHash ? 'trend-hashtag' : ''}">${escapeHtml(t.keyword)}</span>
            <span class="velocity-pill ${velClass}">${velPrefix}${Math.round(t.growth_rate)}%</span>
          </div>
          <div style="display: flex; align-items: center; gap: 10px;">
            <span style="font-size: 0.78rem; color: var(--text-muted);">${t.volume} mentions</span>
            <span class="badge ${t.status === 'Explosive Growth' ? 'badge-danger' : t.status === 'Rising' ? 'badge-success' : 'badge-info'}" style="font-size: 0.68rem;">${t.status}</span>
          </div>
        `;
        risingTrendsList.appendChild(row);
      });
    }

    // 2. Predicted Viral Topics
    if (predictedViralList) {
      predictedViralList.innerHTML = '';
      (summary.predicted_viral_topics || []).forEach(v => {
        const item = document.createElement('div');
        item.className = 'viral-item';
        item.innerHTML = `
          <div class="viral-header">
            <span class="viral-term">${escapeHtml(v.keyword)}</span>
            <span class="viral-score-tag">Virality ${v.virality_score}/100</span>
          </div>
          <div class="viral-bar-bg">
            <div class="viral-bar-fill" style="width: ${Math.max(v.virality_score, 5)}%;"></div>
          </div>
          <div style="display: flex; justify-content: space-between; margin-top: 4px; font-size: 0.72rem; color: var(--text-muted);">
            <span>Velocity: ${Math.round(v.growth_rate)}%</span>
            <span>Status: ${v.status}</span>
          </div>
        `;
        predictedViralList.appendChild(item);
      });
    }

    // 3. Topic Clusters
    if (topicClustersGrid) {
      topicClustersGrid.innerHTML = '';
      (summary.topic_clusters || []).forEach(c => {
        const card = document.createElement('div');
        card.className = 'cluster-card';

        const termsPills = (c.top_terms || [])
          .map(term => `<span class="cluster-term-pill">${escapeHtml(term)}</span>`)
          .join('');

        const sampleQuote = c.sample_snippets?.[0]
          ? `<div class="cluster-quote">"${escapeHtml(c.sample_snippets[0])}"</div>`
          : '';

        card.innerHTML = `
          <div class="cluster-title">
            <span>🔹 ${escapeHtml(c.label)}</span>
            <span style="font-size: 0.74rem; font-weight: 500; color: var(--text-muted); margin-left: auto;">${c.volume} posts</span>
          </div>
          <div class="cluster-terms">${termsPills}</div>
          ${sampleQuote}
        `;
        topicClustersGrid.appendChild(card);
      });
    }

    // 4. Chronological Shifts Timeline
    if (discussionShiftsTimeline) {
      discussionShiftsTimeline.innerHTML = '';
      (summary.chronological_shifts || []).forEach(phase => {
        const card = document.createElement('div');
        card.className = 'shift-phase-card';

        const topicsList = (phase.dominant_topics || [])
          .map(dt => `
            <div class="phase-topic-row">
              <span style="font-family: var(--font-mono);">${escapeHtml(dt.term)}</span>
              <span>${dt.count}x</span>
            </div>
          `)
          .join('');

        card.innerHTML = `
          <div class="phase-header">
            <span class="phase-name">${escapeHtml(phase.phase_name)}</span>
            <span class="phase-count">${phase.post_count} posts</span>
          </div>
          <div class="phase-topics-list">${topicsList}</div>
        `;
        discussionShiftsTimeline.appendChild(card);
      });
    }
  }

  // ══════════════════════════════════════════════════════════════
  // RENDER NETWORK TOPOLOGY & LINK ANALYSIS
  // ══════════════════════════════════════════════════════════════
  let activeNetworkSimulation = null;

  function renderNetwork(summary) {
    const networkEmptyState = document.getElementById('network-empty-state');
    const networkDashboard = document.getElementById('network-dashboard');
    const netNodesCount = document.getElementById('net-nodes-count');
    const netEdgesCount = document.getElementById('net-edges-count');
    const netDensityVal = document.getElementById('net-density-val');
    const netCommunityCount = document.getElementById('net-community-count');
    const kolTableBody = document.getElementById('kol-table-body');
    const communitiesCardsGrid = document.getElementById('communities-cards-grid');
    const spreadCascadeTimeline = document.getElementById('spread-cascade-timeline');
    const canvas = document.getElementById('network-canvas');
    const tooltip = document.getElementById('canvas-tooltip');
    const btnZoomIn = document.getElementById('btn-graph-zoom-in');
    const btnZoomOut = document.getElementById('btn-graph-zoom-out');
    const btnReset = document.getElementById('btn-graph-reset');

    if (!summary || (!summary.nodes?.length && !summary.influencers?.length)) {
      if (networkEmptyState) networkEmptyState.style.display = 'flex';
      if (networkDashboard) networkDashboard.style.display = 'none';
      return;
    }

    if (networkEmptyState) networkEmptyState.style.display = 'none';
    if (networkDashboard) networkDashboard.style.display = 'block';

    // Stats bar
    if (netNodesCount) netNodesCount.textContent = summary.total_nodes;
    if (netEdgesCount) netEdgesCount.textContent = summary.total_edges;
    if (netDensityVal) netDensityVal.textContent = summary.graph_density;
    if (netCommunityCount) netCommunityCount.textContent = summary.communities?.length || 0;

    // 1. Key Opinion Leaders (KOL) Leaderboard
    if (kolTableBody) {
      kolTableBody.innerHTML = '';
      (summary.influencers || []).forEach((inf, idx) => {
        const row = document.createElement('tr');

        let archClass = 'archetype-kol';
        if (inf.archetype === 'Information Broker') archClass = 'archetype-broker';
        else if (inf.archetype === 'Broadcast Amplifier') archClass = 'archetype-amplifier';
        else if (inf.archetype === 'Active Responder') archClass = 'archetype-responder';

        const sentClass = `sentiment-${inf.dominant_sentiment || 'neutral'}`;

        row.innerHTML = `
          <td style="font-family: var(--font-mono); font-weight: 700; color: var(--accent-cyan);">#${idx + 1}</td>
          <td>
            <div style="display: flex; align-items: center; gap: 4px;">
              <span style="font-weight: 600; color: var(--text-primary);">@${escapeHtml(inf.handle)}</span>
              ${inf.verified ? '<span class="verified-check">✓</span>' : ''}
            </div>
            <span style="font-size: 0.72rem; color: var(--text-muted);">${(inf.followers_count || 0).toLocaleString()} followers</span>
          </td>
          <td><span class="archetype-badge ${archClass}">${inf.archetype}</span></td>
          <td style="font-family: var(--font-mono); font-weight: 700; color: var(--accent-amber);">${inf.influence_score}</td>
          <td style="font-family: var(--font-mono);">${inf.pagerank}</td>
          <td style="font-family: var(--font-mono);">${inf.in_degree}</td>
          <td style="font-family: var(--font-mono);">${inf.out_degree}</td>
          <td style="font-family: var(--font-mono);">${inf.betweenness}</td>
          <td><span class="sentiment-badge ${sentClass}">${inf.dominant_sentiment}</span></td>
        `;
        kolTableBody.appendChild(row);
      });
    }

    // 2. Communities Cards
    if (communitiesCardsGrid) {
      communitiesCardsGrid.innerHTML = '';
      (summary.communities || []).forEach(comm => {
        const card = document.createElement('div');
        card.className = 'community-card';
        card.style.borderTopColor = comm.color || '#3b82f6';

        const topPills = (comm.top_influencers || [])
          .map(h => `<span class="tag-pill tag-mention">${escapeHtml(h)}</span>`)
          .join(' ');

        card.innerHTML = `
          <div class="community-title" style="color: ${comm.color || 'var(--text-primary)'};">${escapeHtml(comm.label)}</div>
          <div class="community-members">${comm.member_count} active members • Dominant: <strong>${comm.dominant_sentiment}</strong></div>
          <div style="display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px;">${topPills}</div>
        `;
        communitiesCardsGrid.appendChild(card);
      });
    }

    // 3. Information & Sentiment Spread Cascade Timeline
    if (spreadCascadeTimeline) {
      spreadCascadeTimeline.innerHTML = '';
      if (!summary.spread_cascade || summary.spread_cascade.length === 0) {
        spreadCascadeTimeline.innerHTML = `<div style="color: var(--text-muted); font-size: 0.8rem; padding: 10px;">Direct interaction cascade will populate as replies & quotes are discovered.</div>`;
      } else {
        summary.spread_cascade.forEach(step => {
          const card = document.createElement('div');
          card.className = 'cascade-step-card';
          const sentClass = `sentiment-${step.sentiment || 'neutral'}`;

          card.innerHTML = `
            <div class="step-num-badge">${step.step}</div>
            <div class="cascade-content">
              <div class="cascade-flow-header">
                <strong>${escapeHtml(step.source)}</strong>
                <span class="flow-arrow">──(${step.edge_type})──►</span>
                <strong>${escapeHtml(step.target)}</strong>
                <span class="sentiment-badge ${sentClass}">${step.sentiment}</span>
                <span style="margin-left: auto; font-size: 0.72rem; color: var(--text-muted);">${step.from_segment} ➔ ${step.to_segment}</span>
              </div>
              <div class="cascade-quote">${escapeHtml(step.snippet)}</div>
            </div>
          `;
          spreadCascadeTimeline.appendChild(card);
        });
      }
    }

    // 4. Interactive Canvas Network Graph Engine
    if (canvas && summary.nodes?.length) {
      if (activeNetworkSimulation) {
        activeNetworkSimulation.destroy();
      }
      activeNetworkSimulation = initNetworkCanvas(canvas, tooltip, summary.nodes, summary.links || [], {
        btnZoomIn, btnZoomOut, btnReset
      });
    }
  }

  // ══════════════════════════════════════════════════════════════
  // INTERACTIVE FORCE-DIRECTED CANVAS GRAPH ENGINE
  // ══════════════════════════════════════════════════════════════
  function initNetworkCanvas(canvas, tooltip, rawNodes, rawLinks, controls) {
    const ctx = canvas.getContext('2d');
    let animationFrameId = null;

    // Resize canvas for sharp retina displays
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const width = rect.width || 750;
    const height = 380;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    ctx.scale(dpr, dpr);

    // Pan & Zoom state
    let zoom = 1.0;
    let panX = width / 2;
    let panY = height / 2;
    let isDraggingCanvas = false;
    let dragStartX = 0;
    let dragStartY = 0;
    let hoveredNode = null;
    let draggedNode = null;

    // Build Node objects with positions
    const nodeMap = new Map();
    const nodes = rawNodes.map((rn, i) => {
      const angle = (i / rawNodes.length) * Math.PI * 2;
      const radius = 90 + (i % 3) * 45;
      const node = {
        ...rn,
        x: Math.cos(angle) * radius,
        y: Math.sin(angle) * radius,
        vx: 0,
        vy: 0,
        radius: Math.max(12, Math.min(26, rn.size || 16)),
      };
      nodeMap.set(rn.id, node);
      return node;
    });

    // Build Link objects
    const links = rawLinks.map(rl => ({
      source: nodeMap.get(rl.source) || nodes[0],
      target: nodeMap.get(rl.target) || nodes[nodes.length - 1],
      type: rl.type || 'interaction',
      weight: rl.weight || 1,
    })).filter(l => l.source && l.target && l.source !== l.target);

    // Force Simulation physics loop
    let simulationSteps = 0;
    const maxSteps = 300;

    function stepPhysics() {
      if (simulationSteps > maxSteps) return;
      simulationSteps++;

      const repulsion = 1800;
      const springLength = 110;
      const springStrength = 0.04;
      const damping = 0.86;
      const centerGravity = 0.015;

      // 1. Coulomb node-to-node repulsion
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const n1 = nodes[i];
          const n2 = nodes[j];
          const dx = n2.x - n1.x;
          const dy = n2.y - n1.y;
          const distSq = dx * dx + dy * dy || 1;
          const dist = Math.sqrt(distSq);
          if (dist < 320) {
            const force = repulsion / distSq;
            const fx = (dx / dist) * force;
            const fy = (dy / dist) * force;
            n1.vx -= fx;
            n1.vy -= fy;
            n2.vx += fx;
            n2.vy += fy;
          }
        }
      }

      // 2. Spring link attraction
      for (const link of links) {
        const dx = link.target.x - link.source.x;
        const dy = link.target.y - link.source.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const displacement = dist - springLength;
        const force = displacement * springStrength;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        link.source.vx += fx;
        link.source.vy += fy;
        link.target.vx -= fx;
        link.target.vy -= fy;
      }

      // 3. Center gravity & integrate
      for (const n of nodes) {
        if (n === draggedNode) continue;
        n.vx -= n.x * centerGravity;
        n.vy -= n.y * centerGravity;
        n.vx *= damping;
        n.vy *= damping;
        n.x += n.vx;
        n.y += n.vy;
      }
    }

    function render() {
      stepPhysics();

      ctx.save();
      ctx.clearRect(0, 0, width, height);

      // Background subtle grid
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.02)';
      ctx.lineWidth = 1;
      const gridSize = 40 * zoom;
      const offsetX = panX % gridSize;
      const offsetY = panY % gridSize;
      ctx.beginPath();
      for (let x = offsetX; x < width; x += gridSize) {
        ctx.moveTo(x, 0); ctx.lineTo(x, height);
      }
      for (let y = offsetY; y < height; y += gridSize) {
        ctx.moveTo(0, y); ctx.lineTo(width, y);
      }
      ctx.stroke();

      // Apply transform
      ctx.translate(panX, panY);
      ctx.scale(zoom, zoom);

      // Draw Links
      ctx.lineWidth = 1.5;
      for (const link of links) {
        ctx.strokeStyle = 'rgba(0, 240, 255, 0.22)';
        ctx.beginPath();
        ctx.moveTo(link.source.x, link.source.y);
        ctx.lineTo(link.target.x, link.target.y);
        ctx.stroke();

        // Draw arrow tip
        const dx = link.target.x - link.source.x;
        const dy = link.target.y - link.source.y;
        const angle = Math.atan2(dy, dx);
        const arrowDist = link.target.radius + 6;
        const ax = link.target.x - Math.cos(angle) * arrowDist;
        const ay = link.target.y - Math.sin(angle) * arrowDist;

        ctx.fillStyle = 'rgba(0, 240, 255, 0.5)';
        ctx.beginPath();
        ctx.moveTo(ax, ay);
        ctx.lineTo(ax - 7 * Math.cos(angle - Math.PI / 6), ay - 7 * Math.sin(angle - Math.PI / 6));
        ctx.lineTo(ax - 7 * Math.cos(angle + Math.PI / 6), ay - 7 * Math.sin(angle + Math.PI / 6));
        ctx.closePath();
        ctx.fill();
      }

      // Draw Nodes
      for (const n of nodes) {
        const isHovered = n === hoveredNode;

        // Outer glow
        if (isHovered) {
          ctx.beginPath();
          ctx.arc(n.x, n.y, n.radius + 6, 0, Math.PI * 2);
          ctx.fillStyle = 'rgba(0, 240, 255, 0.35)';
          ctx.fill();
        }

        // Node circle
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.radius, 0, Math.PI * 2);
        ctx.fillStyle = n.color || '#3b82f6';
        ctx.fill();
        ctx.strokeStyle = isHovered ? '#ffffff' : 'rgba(255, 255, 255, 0.4)';
        ctx.lineWidth = isHovered ? 2.5 : 1.5;
        ctx.stroke();

        // Label
        ctx.font = isHovered ? 'bold 11px JetBrains Mono, monospace' : '10px JetBrains Mono, monospace';
        ctx.fillStyle = isHovered ? '#ffffff' : 'rgba(255, 255, 255, 0.85)';
        ctx.textAlign = 'center';
        ctx.fillText(n.label, n.x, n.y + n.radius + 13);
      }

      ctx.restore();
      animationFrameId = requestAnimationFrame(render);
    }

    animationFrameId = requestAnimationFrame(render);

    // Coordinate helpers
    function toWorldCoords(clientX, clientY) {
      const b = canvas.getBoundingClientRect();
      const screenX = clientX - b.left;
      const screenY = clientY - b.top;
      return {
        x: (screenX - panX) / zoom,
        y: (screenY - panY) / zoom,
        screenX,
        screenY,
      };
    }

    function findNodeAt(worldX, worldY) {
      for (let i = nodes.length - 1; i >= 0; i--) {
        const n = nodes[i];
        const dx = worldX - n.x;
        const dy = worldY - n.y;
        if (Math.sqrt(dx * dx + dy * dy) <= n.radius + 4) {
          return n;
        }
      }
      return null;
    }

    // Mouse Listeners
    function onMouseDown(e) {
      const { x, y, screenX, screenY } = toWorldCoords(e.clientX, e.clientY);
      const hit = findNodeAt(x, y);
      if (hit) {
        draggedNode = hit;
        simulationSteps = 0; // awaken physics
      } else {
        isDraggingCanvas = true;
        dragStartX = screenX - panX;
        dragStartY = screenY - panY;
        canvas.style.cursor = 'grabbing';
      }
    }

    function onMouseMove(e) {
      const { x, y, screenX, screenY } = toWorldCoords(e.clientX, e.clientY);

      if (draggedNode) {
        draggedNode.x = x;
        draggedNode.y = y;
        draggedNode.vx = 0;
        draggedNode.vy = 0;
        return;
      }

      if (isDraggingCanvas) {
        panX = screenX - dragStartX;
        panY = screenY - dragStartY;
        return;
      }

      // Hover check
      const hit = findNodeAt(x, y);
      if (hit !== hoveredNode) {
        hoveredNode = hit;
        canvas.style.cursor = hit ? 'pointer' : 'grab';

        if (hit && tooltip) {
          tooltip.style.display = 'block';
          tooltip.style.left = `${Math.min(width - 230, screenX + 12)}px`;
          tooltip.style.top = `${Math.min(height - 120, screenY + 12)}px`;
          tooltip.innerHTML = `
            <div style="font-weight: 700; color: var(--accent-cyan); margin-bottom: 2px;">
              ${escapeHtml(hit.name || hit.label)}
            </div>
            <div style="color: var(--text-muted); font-size: 0.72rem; margin-bottom: 4px;">
              ${hit.label} • ${hit.archetype}
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 4px; font-size: 0.72rem;">
              <span>Score: <strong>${hit.score}</strong></span>
              <span>PageRank: <strong>${hit.pagerank}</strong></span>
              <span>In-Degree: <strong>${hit.inDegree}</strong></span>
              <span>Out-Degree: <strong>${hit.outDegree}</strong></span>
            </div>
            <div style="margin-top: 4px; font-size: 0.7rem; color: var(--accent-emerald);">
              Tone: ${hit.sentiment}
            </div>
          `;
        } else if (tooltip) {
          tooltip.style.display = 'none';
        }
      }
    }

    function onMouseUp() {
      draggedNode = null;
      isDraggingCanvas = false;
      canvas.style.cursor = hoveredNode ? 'pointer' : 'grab';
    }

    function onWheel(e) {
      e.preventDefault();
      const zoomFactor = e.deltaY < 0 ? 1.1 : 0.9;
      zoom = Math.max(0.4, Math.min(3.0, zoom * zoomFactor));
    }

    canvas.addEventListener('mousedown', onMouseDown);
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
    canvas.addEventListener('wheel', onWheel, { passive: false });

    // Controls
    if (controls.btnZoomIn) {
      controls.btnZoomIn.onclick = () => { zoom = Math.min(3.0, zoom * 1.25); };
    }
    if (controls.btnZoomOut) {
      controls.btnZoomOut.onclick = () => { zoom = Math.max(0.4, zoom * 0.8); };
    }
    if (controls.btnReset) {
      controls.btnReset.onclick = () => {
        zoom = 1.0;
        panX = width / 2;
        panY = height / 2;
        simulationSteps = 0;
      };
    }

    return {
      destroy() {
        if (animationFrameId) cancelAnimationFrame(animationFrameId);
        canvas.removeEventListener('mousedown', onMouseDown);
        window.removeEventListener('mousemove', onMouseMove);
        window.removeEventListener('mouseup', onMouseUp);
        canvas.removeEventListener('wheel', onWheel);
      }
    };
  }

  // Copy raw JSON
  btnExportJson.addEventListener('click', () => {
    if (!currentScrapedData) {
      alert('No scraped data available to copy.');
      return;
    }
    navigator.clipboard.writeText(JSON.stringify(currentScrapedData, null, 2))
      .then(() => alert('JSON copied to clipboard!'))
      .catch(err => alert('Failed to copy: ' + err));
  });

  // Modal handlers
  btnOpenAccounts.addEventListener('click', async () => {
    accountsModal.style.display = 'flex';
    try {
      const res = await fetch('/api/scraper/accounts');
      if (res.ok) {
        const data = await res.json();
        accountsContentInput.value = data.content || '';
      }
    } catch (e) {
      console.warn(e);
    }
  });

  function closeModal() {
    accountsModal.style.display = 'none';
  }
  btnCloseModal.addEventListener('click', closeModal);
  btnCancelModal.addEventListener('click', closeModal);

  btnSaveAccounts.addEventListener('click', async () => {
    const content = accountsContentInput.value;
    try {
      const res = await fetch('/api/scraper/accounts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content })
      });
      const data = await res.json();
      if (res.ok) {
        alert(data.message || 'Accounts file saved successfully!');
        closeModal();
        fetchStatus();
      } else {
        alert(data.detail || 'Failed to save accounts.');
      }
    } catch (err) {
      alert('Error saving accounts: ' + err.message);
    }
  });
});
