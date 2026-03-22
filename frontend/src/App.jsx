import { useEffect, useState } from "react";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function apiFetch(path, options = {}, token) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  });

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    try {
      const payload = await response.json();
      detail = typeof payload.detail === "string" ? payload.detail : JSON.stringify(payload.detail);
    } catch {
      detail = await response.text();
    }
    throw new Error(detail);
  }

  if (response.status === 204) {
    return null;
  }
  return response.json();
}

function formatListDate(value) {
  if (!value) {
    return "";
  }
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatDetailDate(value) {
  if (!value) {
    return "Unknown time";
  }
  return new Intl.DateTimeFormat(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function cleanBodyText(value) {
  if (!value) {
    return "No body text captured.";
  }

  const footerPatterns = [
    /unsubscribe/i,
    /manage preferences/i,
    /privacy policy/i,
    /terms of service/i,
    /view in browser/i,
    /download the app/i,
    /^©/i,
  ];

  const cleaned = value
    .replace(/\[image:[^\]]+\]/gi, "")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/gi, "$1")
    .replace(/\(\s*https?:\/\/[^)]+\)/gi, "")
    .replace(/https?:\/\/\S+/gi, "")
    .replace(/\r/g, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();

  const lines = cleaned
    .split("\n")
    .map((line) => line.replace(/\s{2,}/g, " ").trim())
    .filter(Boolean)
    .filter((line) => !footerPatterns.some((pattern) => pattern.test(line)))
    .filter((line) => {
      const alphaNumeric = line.replace(/[^a-z0-9]/gi, "");
      return alphaNumeric.length >= 3;
    });

  return lines.join("\n").trim();
}

function getParagraphs(value) {
  return cleanBodyText(value)
    .split(/\n\s*\n/)
    .map((part) => part.trim())
    .filter(Boolean);
}

function getTone(action) {
  if (action === "archive" || action === "keep") {
    return "positive";
  }
  if (action === "trash") {
    return "danger";
  }
  return "neutral";
}

function getInitials(value) {
  if (!value) {
    return "?";
  }
  return value
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
}

function formatCount(value) {
  return new Intl.NumberFormat().format(value || 0);
}

function clampText(value, maxLength = 140) {
  if (!value) {
    return "";
  }
  return value.length > maxLength ? `${value.slice(0, maxLength).trim()}...` : value;
}

function formatRecommendationSource(source) {
  if (!source) {
    return "Unknown";
  }

  const labels = {
    rule: "Rules",
    hybrid: "Rules + Similarity",
    llm: "LLM",
  };
  return labels[source] || source;
}

function describeRecommendationSource(source) {
  const descriptions = {
    rule: "Protected patterns and deterministic inbox rules produced this recommendation.",
    hybrid: "Rules were adjusted using similar past email behavior and safety guardrails.",
    llm: "An LLM handled this ambiguous case after the deterministic rules were not confident enough.",
  };
  return descriptions[source] || "Recommendation source unavailable.";
}

export default function App() {
  const [token, setToken] = useState(() => localStorage.getItem("gmail_cleanup_token") || "");
  const [auth, setAuth] = useState(null);
  const [emails, setEmails] = useState([]);
  const [selectedEmail, setSelectedEmail] = useState(null);
  const [similarEmails, setSimilarEmails] = useState([]);
  const [actionHistory, setActionHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [labelInput, setLabelInput] = useState("");
  const [confirmHighRisk, setConfirmHighRisk] = useState(false);
  const [syncResult, setSyncResult] = useState(null);
  const [actionInFlight, setActionInFlight] = useState("");

  function resetMailboxState() {
    setEmails([]);
    setSelectedEmail(null);
    setSimilarEmails([]);
    setActionHistory([]);
    setLabelInput("");
    setConfirmHighRisk(false);
    setSyncResult(null);
  }

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const nextToken = params.get("token");
    if (nextToken) {
      localStorage.setItem("gmail_cleanup_token", nextToken);
      setToken(nextToken);
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, []);

  useEffect(() => {
    if (!token) {
      setAuth(null);
      setError("");
      resetMailboxState();
      return;
    }

    apiFetch("/auth/me", {}, token)
      .then(setAuth)
      .catch((err) => {
        setError(err.message);
        localStorage.removeItem("gmail_cleanup_token");
        setToken("");
      });
  }, [token]);

  useEffect(() => {
    if (token) {
      loadEmails(token);
    }
  }, [token]);

  async function loadEmails(activeToken) {
    setLoading(true);
    try {
      const data = await apiFetch("/emails", {}, activeToken);
      setEmails(data);
      if (data.length > 0) {
        const nextSelectedId = selectedEmail?.id;
        const nextSelectedEmail =
          (nextSelectedId && data.find((item) => item.id === nextSelectedId)) || data[0];
        await loadEmailDetail(nextSelectedEmail.id, activeToken);
      } else {
        setSelectedEmail(null);
        setSimilarEmails([]);
        setActionHistory([]);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadEmailDetail(emailId, activeToken = token) {
    try {
      const [detail, similar, actions] = await Promise.all([
        apiFetch(`/emails/${emailId}`, {}, activeToken),
        apiFetch(`/emails/${emailId}/similar`, {}, activeToken).catch(() => []),
        apiFetch(`/emails/${emailId}/actions`, {}, activeToken),
      ]);
      setSelectedEmail(detail);
      setSimilarEmails(similar);
      setActionHistory(actions);
      setLabelInput("");
      setConfirmHighRisk(false);
    } catch (err) {
      setError(err.message);
    }
  }

  async function startGoogleLogin() {
    setError("");
    try {
      const data = await apiFetch("/auth/google/login");
      window.location.href = data.auth_url;
    } catch (err) {
      setError(err.message);
    }
  }

  async function useDemoInbox() {
    setError("");
    setNotice("");
    try {
      const login = await apiFetch("/auth/dev-login", { method: "POST" });
      localStorage.setItem("gmail_cleanup_token", login.token);
      setToken(login.token);
      await apiFetch("/emails/dev-seed", { method: "POST" }, login.token);
      setNotice("Demo inbox loaded. Review the recommendation source on each sample email.");
      await loadEmails(login.token);
    } catch (err) {
      setError(err.message);
    }
  }

  async function syncEmails() {
    setSyncing(true);
    setError("");
    setNotice("");
    try {
      const result = await apiFetch("/emails/sync", { method: "POST" }, token);
      setSyncResult(result);
      setNotice(`Sync complete: ${result.created} created, ${result.updated} updated.`);
      await loadEmails(token);
    } catch (err) {
      setError(err.message);
    } finally {
      setSyncing(false);
    }
  }

  async function executeAction(action) {
    if (!selectedEmail) {
      return;
    }

    setActionInFlight(action);
    setError("");
    setNotice("");
    try {
      await apiFetch(
        `/emails/${selectedEmail.id}/execute`,
        {
          method: "POST",
          body: JSON.stringify({
            action,
            label_names: action === "label" ? labelInput.split(",").map((item) => item.trim()).filter(Boolean) : [],
            confirm_high_risk: confirmHighRisk,
          }),
        },
        token,
      );
      const label = {
        archive: "archived to Gmail",
        trash: "moved to Gmail trash",
        mark_read: "marked as read in Gmail",
        label: "labels applied in Gmail",
      }[action] || "action applied";
      setNotice(`Email ${label}.`);
      await loadEmails(token);
    } catch (err) {
      setError(err.message);
    } finally {
      setActionInFlight("");
    }
  }

  function signOut() {
    localStorage.removeItem("gmail_cleanup_token");
    setToken("");
    setAuth(null);
    setNotice("");
    setError("");
    resetMailboxState();
  }

  const selectedLabels = selectedEmail?.gmail_labels
    ? selectedEmail.gmail_labels.split(",").map((item) => item.trim()).filter(Boolean)
    : [];
  const selectedParagraphs = selectedEmail ? getParagraphs(selectedEmail.body_text) : [];
  const selectedSender = selectedEmail?.sender_name || selectedEmail?.sender_email || "Unknown sender";

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <p className="eyebrow">Inbox operations</p>
          <h1>Gmail Cleanup AI</h1>
          <p className="muted">
            Review-first inbox cleanup with Gmail sync, recommendations, and guarded actions.
          </p>
        </div>

        <div className="panel">
          <div className="account-head">
            <div>
              <p className="eyebrow">Workspace</p>
              <h2>Mailbox</h2>
            </div>
            {auth?.user ? <span className="status-dot online">Live</span> : null}
          </div>
          {auth?.user ? (
            <>
              <div className="account-summary">
                <div className="account-avatar">{getInitials(auth.user.name || auth.user.email)}</div>
                <div>
                  <strong>{auth.user.name || auth.user.email}</strong>
                  <p className="muted">{auth.user.email}</p>
                </div>
              </div>
              <p className="muted">
                {auth.gmail_account ? `Connected Gmail: ${auth.gmail_account.email}` : "No Gmail account connected"}
              </p>
              <div className="button-row">
                <button onClick={syncEmails} disabled={syncing}>
                  {syncing ? "Syncing..." : "Sync inbox"}
                </button>
                <button className="secondary" onClick={useDemoInbox}>
                  Load demo inbox
                </button>
                <button className="secondary" onClick={signOut}>
                  Sign out
                </button>
              </div>
              {syncResult ? (
                <div className="sync-banner">
                  <strong>Last sync</strong>
                  <span>{syncResult.created} created</span>
                  <span>{syncResult.updated} updated</span>
                </div>
              ) : null}
            </>
          ) : (
            <>
              <p className="muted">Connect Google to sync and act on real Gmail messages.</p>
              <div className="button-stack">
                <button onClick={startGoogleLogin}>Sign in with Google</button>
                <button className="secondary" onClick={useDemoInbox}>
                  Use demo inbox
                </button>
              </div>
            </>
          )}
        </div>

        <div className="panel list-panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Inbox</p>
              <h2>Emails</h2>
            </div>
            <span className="count-pill">{formatCount(emails.length)}</span>
          </div>
          {loading ? <p className="muted">Loading…</p> : null}
          <div className="email-list">
            {emails.map((email) => (
              <button
                key={email.id}
                className={`email-card ${selectedEmail?.id === email.id ? "active" : ""}`}
                onClick={() => loadEmailDetail(email.id)}
              >
                <div className="email-card-shell">
                  <div className="sender-avatar">
                    {getInitials(email.sender_name || email.sender_email)}
                  </div>
                  <div className="email-card-copy">
                    <div className="email-card-row">
                      <strong>{email.sender_name || email.sender_email || "Unknown sender"}</strong>
                      <time>{formatListDate(email.received_at || email.created_at)}</time>
                    </div>
                    <span className="email-card-subject">{email.subject || "(No subject)"}</span>
                    <p>{clampText(email.snippet || "No preview available.", 100)}</p>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>
      </aside>

      <main className="content">
        <section className="topbar">
          <div>
            <p className="eyebrow">Reader</p>
            <h2>Review queue</h2>
          </div>
          <div className="topbar-stats">
            <div className="stat-chip">
              <span>Total</span>
              <strong>{formatCount(emails.length)}</strong>
            </div>
            <div className="stat-chip">
              <span>Connected</span>
              <strong>{auth?.gmail_account ? "Yes" : "No"}</strong>
            </div>
          </div>
        </section>
        {error ? <div className="alert error">{error}</div> : null}
        {notice ? <div className="alert success">{notice}</div> : null}
        {!selectedEmail ? (
          <div className="empty-state">
            <h2>No email selected</h2>
            <p>Connect Gmail and sync to review recommendations.</p>
          </div>
        ) : (
          <>
            <section className="mail-layout">
              <div className="mail-main">
                <div className="panel mail-header">
                  <div className="hero-sender">
                    <div className="sender-avatar large">{getInitials(selectedSender)}</div>
                    <div className="sender-copy">
                      <p className="eyebrow">Email detail</p>
                      <h2>{selectedEmail.subject || "(No subject)"}</h2>
                      <div className="sender-meta">
                        <strong>{selectedSender}</strong>
                        <span className="dot-separator" />
                        <span className="muted">{selectedEmail.sender_email || "Unknown sender"}</span>
                      </div>
                    </div>
                  </div>
                  <div className="mail-header-side">
                    <span className="status-pill">{selectedEmail.is_read ? "Read" : "Unread"}</span>
                    <time>{formatDetailDate(selectedEmail.received_at || selectedEmail.created_at)}</time>
                  </div>
                </div>

                <div className="panel message-panel">
                  <div className="message-header">
                    <div className="chip-row">
                      {selectedLabels.length > 0 ? (
                        selectedLabels.map((label) => (
                          <span key={label} className="chip">
                            {label}
                          </span>
                        ))
                      ) : (
                        <span className="chip muted-chip">No labels</span>
                      )}
                    </div>
                    {selectedEmail.has_unsubscribe ? (
                      <span className="chip warning-chip">Unsubscribe</span>
                    ) : null}
                  </div>
                  <div className="message-snippet">{selectedEmail.snippet || "No preview available."}</div>
                  <div className="message-body">
                    {selectedParagraphs.length > 0 ? (
                      selectedParagraphs.map((paragraph, index) => <p key={index}>{paragraph}</p>)
                    ) : (
                      <p>No body text captured.</p>
                    )}
                  </div>
                </div>

                <div className="panel similar-panel">
                  <div className="panel-header">
                    <h2>Similar emails</h2>
                    <span className="count-pill">{similarEmails.length}</span>
                  </div>
                  {similarEmails.length === 0 ? <p className="muted">No similar emails yet.</p> : null}
                  {similarEmails.map((item) => (
                    <div key={item.id} className="similar-card">
                      <div className="similar-card-top">
                        <strong>{item.subject || "(No subject)"}</strong>
                        <span className={`tone-pill ${getTone(item.last_user_action)}`}>
                          {item.last_user_action || "none"}
                        </span>
                      </div>
                      <p>{clampText(item.sender_email, 64)}</p>
                      <p className="muted">Distance {item.distance.toFixed(3)}</p>
                    </div>
                  ))}
                </div>
              </div>

              <div className="mail-side">
                <div className={`panel recommendation-panel recommendation-panel-${getTone(selectedEmail.classification?.suggested_action)}`}>
                  <div className="recommendation-header">
                    <div>
                      <p className="eyebrow">Recommendation Source</p>
                      <h2>{selectedEmail.classification?.suggested_action || "review"}</h2>
                    </div>
                    <span className="tone-pill neutral">
                      {formatRecommendationSource(selectedEmail.classification?.source)}
                    </span>
                  </div>
                  <h2>Recommendation</h2>
                  <p className="muted source-copy">
                    {describeRecommendationSource(selectedEmail.classification?.source)}
                  </p>
                  <div className="stat-grid">
                    <div>
                      <span className="stat-label">Importance</span>
                      <strong>{selectedEmail.classification?.importance || "unknown"}</strong>
                    </div>
                    <div>
                        <span className="stat-label">Confidence</span>
                        <strong>
                          {selectedEmail.classification?.confidence
                            ? selectedEmail.classification.confidence.toFixed(2)
                            : "n/a"}
                        </strong>
                      </div>
                    <div>
                      <span className="stat-label">Category</span>
                      <strong>{selectedEmail.classification?.category || "unknown"}</strong>
                    </div>
                  </div>
                  <div className="reason-box">
                    {selectedEmail.classification?.reason || "No recommendation yet."}
                  </div>
                  <div className="chip-row">
                    {selectedEmail.risk_flags?.length ? (
                      selectedEmail.risk_flags.map((flag) => (
                        <span key={flag} className="chip risk-chip">
                          {flag}
                        </span>
                      ))
                    ) : (
                      <span className="chip muted-chip">No risk flags</span>
                    )}
                  </div>
                </div>

                <div className="panel actions-panel">
                  <p className="eyebrow">Human review</p>
                  <h2>Cleanup actions</h2>
                  <div className="button-stack">
                    <button
                      onClick={() => executeAction("archive")}
                      disabled={Boolean(actionInFlight)}
                    >
                      {actionInFlight === "archive" ? "Archiving..." : "Archive"}
                    </button>
                    <button
                      onClick={() => executeAction("trash")}
                      className="danger"
                      disabled={Boolean(actionInFlight)}
                    >
                      {actionInFlight === "trash" ? "Moving..." : "Move to trash"}
                    </button>
                    <button
                      onClick={() => executeAction("mark_read")}
                      className="secondary"
                      disabled={Boolean(actionInFlight)}
                    >
                      {actionInFlight === "mark_read" ? "Updating..." : "Mark as read"}
                    </button>
                  </div>
                  <label className="field">
                    <span>Labels</span>
                    <input
                      value={labelInput}
                      onChange={(event) => setLabelInput(event.target.value)}
                      placeholder="Finance, Follow Up"
                    />
                  </label>
                  <button
                    className="secondary full-width"
                    onClick={() => executeAction("label")}
                    disabled={Boolean(actionInFlight)}
                  >
                    {actionInFlight === "label" ? "Applying..." : "Apply labels"}
                  </button>
                  <label className="checkbox-inline">
                    <input
                      type="checkbox"
                      checked={confirmHighRisk}
                      onChange={(event) => setConfirmHighRisk(event.target.checked)}
                    />
                    <span>Allow high-risk archive or trash</span>
                  </label>
                </div>

                <div className="panel history-panel">
                  <div className="panel-header">
                    <h2>Action history</h2>
                    <span className="count-pill">{actionHistory.length}</span>
                  </div>
                  {actionHistory.length === 0 ? <p className="muted">No actions recorded yet.</p> : null}
                  {actionHistory.map((item) => (
                    <div key={item.id} className="history-row">
                      <div>
                        <strong>{item.action_taken}</strong>
                        <p className="muted">{item.action_source}</p>
                      </div>
                      <time>{formatDetailDate(item.created_at)}</time>
                    </div>
                  ))}
                </div>
              </div>
            </section>
          </>
        )}
      </main>
    </div>
  );
}
