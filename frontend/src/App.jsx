import { useEffect, useRef, useState } from "react";

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

  const numericEntityDecoded = value
    .replace(/&#x([0-9a-f]+);/gi, (_, hex) => {
      const codePoint = Number.parseInt(hex, 16);
      return Number.isNaN(codePoint) ? " " : String.fromCodePoint(codePoint);
    })
    .replace(/&#(\d+);/g, (_, num) => {
      const codePoint = Number.parseInt(num, 10);
      return Number.isNaN(codePoint) ? " " : String.fromCodePoint(codePoint);
    });

  const withoutHtml = numericEntityDecoded
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/(p|div|li|h1|h2|h3|h4|h5|h6|tr|section|article)>/gi, "\n")
    .replace(/<li[^>]*>/gi, "• ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&#39;/gi, "'")
    .replace(/&quot;/gi, '"')
    .replace(/[\u00a0\u200b-\u200f\u2060\ufeff]/g, " ");

  const footerPatterns = [
    /unsubscribe/i,
    /manage preferences/i,
    /privacy policy/i,
    /terms of service/i,
    /view in browser/i,
    /download the app/i,
    /^©/i,
  ];

  const cleaned = withoutHtml
    .replace(/\[image:[^\]]+\]/gi, "")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/gi, "$1")
    .replace(/\(\s*https?:\/\/[^)]+\)/gi, "")
    .replace(/https?:\/\/\S+/gi, "")
    .replace(/\r/g, "")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n[ \t]+/g, "\n")
    .replace(/[ \t]{2,}/g, " ")
    .replace(/^[•\s]+$/gm, "")
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
  const skipNextTokenLoadRef = useRef(false);
  const preferredEmailIdRef = useRef(null);
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
  const [archiveReviewOpen, setArchiveReviewOpen] = useState(false);
  const [archiveCandidates, setArchiveCandidates] = useState([]);
  const [archiveReviewLoading, setArchiveReviewLoading] = useState(false);
  const [archiveConfirming, setArchiveConfirming] = useState(false);
  const [demoLoading, setDemoLoading] = useState(false);

  function resetMailboxState() {
    setEmails([]);
    setSelectedEmail(null);
    setSimilarEmails([]);
    setActionHistory([]);
    setLabelInput("");
    setConfirmHighRisk(false);
    setSyncResult(null);
    setArchiveReviewOpen(false);
    setArchiveCandidates([]);
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
      if (skipNextTokenLoadRef.current) {
        skipNextTokenLoadRef.current = false;
        return;
      }
      loadEmails(token, { preferredEmailId: preferredEmailIdRef.current });
      preferredEmailIdRef.current = null;
    }
  }, [token]);

  async function loadEmails(activeToken, options = {}) {
    const { preferredEmailId } = options;
    setLoading(true);
    try {
      const data = await apiFetch("/emails", {}, activeToken);
      setEmails(data);
      if (data.length > 0) {
        const nextSelectedId = preferredEmailId || selectedEmail?.id;
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
    setDemoLoading(true);
    setError("");
    setNotice("");
    try {
      const login = await apiFetch("/auth/dev-login", { method: "POST" });
      resetMailboxState();
      const seeded = await apiFetch("/emails/dev-seed", { method: "POST" }, login.token);
      const firstSeededEmailId = seeded?.emails?.[0]?.id;
      localStorage.setItem("gmail_cleanup_token", login.token);
      preferredEmailIdRef.current = firstSeededEmailId || null;
      skipNextTokenLoadRef.current = true;
      setToken(login.token);
      setAuth({
        user: login.user,
        gmail_account: null,
      });
      setNotice("Demo inbox loaded. Review the recommendation source on each sample email.");
      await loadEmails(login.token, { preferredEmailId: firstSeededEmailId });
    } catch (err) {
      setError(err.message);
    } finally {
      setDemoLoading(false);
    }
  }

  async function syncEmails() {
    setSyncing(true);
    setError("");
    setNotice("");
    try {
      const result = await apiFetch("/emails/sync", { method: "POST" }, token);
      setSyncResult(result);
      setArchiveReviewOpen(false);
      setArchiveCandidates([]);
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

  async function reviewArchiveCandidates() {
    setArchiveReviewLoading(true);
    setError("");
    setNotice("");
    try {
      const result = await apiFetch("/emails/archive-candidates", {}, token);
      const nextCandidates = result.emails || [];
      setArchiveCandidates(nextCandidates);
      setArchiveReviewOpen(true);
      if (nextCandidates.length > 0) {
        await loadEmailDetail(nextCandidates[0].id);
        setNotice(`Review these ${nextCandidates.length} emails before confirming archive.`);
      } else {
        setNotice("No emails are available for archive review right now.");
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setArchiveReviewLoading(false);
    }
  }

  async function confirmArchiveCandidates() {
    if (archiveCandidates.length === 0) {
      return;
    }

    setArchiveConfirming(true);
    setError("");
    setNotice("");
    try {
      const reviewedCount = archiveCandidates.length;
      const result = await apiFetch(
        "/emails/archive-candidates/archive",
        {
          method: "POST",
          body: JSON.stringify({
            email_ids: archiveCandidates.map((item) => item.id),
          }),
        },
        token,
      );
      setArchiveReviewOpen(false);
      setArchiveCandidates([]);
      setNotice(
        result.archived_count > 0
          ? `Archived ${result.archived_count} of ${reviewedCount} reviewed emails to Gmail.`
          : "No reviewed emails were archived."
      );
      await loadEmails(token);
    } catch (err) {
      setError(err.message);
    } finally {
      setArchiveConfirming(false);
    }
  }

  function exitArchiveReview() {
    setArchiveReviewOpen(false);
    setArchiveCandidates([]);
    setNotice("");
  }

  const selectedLabels = selectedEmail?.gmail_labels
    ? selectedEmail.gmail_labels.split(",").map((item) => item.trim()).filter(Boolean)
    : [];
  const selectedParagraphs = selectedEmail ? getParagraphs(selectedEmail.body_text) : [];
  const selectedSender = selectedEmail?.sender_name || selectedEmail?.sender_email || "Unknown sender";
  const selectedSource = formatRecommendationSource(selectedEmail?.classification?.source);
  const isSignedOut = !auth?.user;

  if (isSignedOut) {
    return (
      <div className="landing-shell">
        {demoLoading ? (
          <div className="loading-overlay">
            <div className="loading-dialog">
              <span className="button-loading" />
              <div>
                <strong>Preparing demo inbox</strong>
                <p>Loading sample emails and recommendations.</p>
              </div>
            </div>
          </div>
        ) : null}
        <section className="landing-hero">
          <div className="landing-copy">
            <p className="eyebrow">AI Gmail Assistant</p>
            <h1>Inbox cleanup with guardrails.</h1>
            <p className="landing-summary">
              Triage clutter, protect important messages, and review recommended actions before anything is archived in Gmail.
            </p>
            <div className="landing-actions">
              <button onClick={startGoogleLogin}>Connect Gmail</button>
              <button className="secondary" onClick={useDemoInbox}>
                Try demo inbox
              </button>
            </div>
            <div className="landing-proof">
              <span>LLM + rules + similarity</span>
              <span>Review-first workflow</span>
              <span>No permanent delete flow</span>
            </div>
          </div>
          <div className="landing-preview">
            <div className="preview-window">
              <div className="preview-topbar">
                <span className="preview-dot" />
                <span className="preview-dot" />
                <span className="preview-dot" />
              </div>
              <div className="preview-card">
                <div>
                  <p className="eyebrow">Recommendation</p>
                  <h2>archive</h2>
                  <p className="preview-meta">confidence 0.72 · category update</p>
                </div>
                <span className="tone-pill neutral">LLM</span>
              </div>
              <div className="preview-message">
                <strong>Your team workspace digest</strong>
                <p>Low-risk update. Routed to AI because deterministic rules were below the confidence threshold.</p>
                <div className="preview-signal-grid">
                  <div className="preview-signal">
                    <span>sender</span>
                    <strong>hello@nimbus-app.demo</strong>
                  </div>
                  <div className="preview-signal">
                    <span>labels</span>
                    <strong>INBOX</strong>
                  </div>
                  <div className="preview-signal">
                    <span>risk flags</span>
                    <strong>none</strong>
                  </div>
                  <div className="preview-signal">
                    <span>policy</span>
                    <strong>llm_fallback</strong>
                  </div>
                </div>
              </div>
              <div className="preview-card muted-surface">
                <div>
                  <p className="eyebrow">Protected</p>
                  <h2>keep</h2>
                  <p className="preview-meta">confidence 0.97 · category important</p>
                </div>
                <span className="tone-pill positive">Rules</span>
              </div>
            </div>
          </div>
        </section>

        {error ? <div className="alert error">{error}</div> : null}
        {notice ? <div className="alert success">{notice}</div> : null}

        <section className="landing-steps">
          <div className="step-card">
            <span className="step-index">01</span>
            <div>
              <p className="eyebrow">Protect first</p>
              <h3>Deterministic safety guardrails</h3>
              <p>Important email is protected by explicit rules before any AI recommendation is trusted.</p>
            </div>
          </div>
          <div className="step-card">
            <span className="step-index">02</span>
            <div>
              <p className="eyebrow">Review clearly</p>
              <h3>Inspect before archive</h3>
              <p>Open each message, see the recommendation source, and check similar emails before taking action.</p>
            </div>
          </div>
          <div className="step-card">
            <span className="step-index">03</span>
            <div>
              <p className="eyebrow">Start quickly</p>
              <h3>Demo inbox available</h3>
              <p>Try the full workflow immediately with sample emails if you do not want to connect Gmail yet.</p>
            </div>
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="app-shell">
      {demoLoading ? (
        <div className="loading-overlay">
          <div className="loading-dialog">
            <span className="button-loading" />
            <div>
              <strong>Preparing demo inbox</strong>
              <p>Loading sample emails and recommendations.</p>
            </div>
          </div>
        </div>
      ) : null}
      <header className="workspace-bar">
        <div className="workspace-bar-copy">
          <p className="eyebrow">AI Inbox Triage</p>
          <div className="workspace-title-row">
            <h1>Gmail Cleanup AI</h1>
            <span className="workspace-badge">Review-first</span>
          </div>
          <p className="muted">
            Review-first inbox cleanup with recommendations, protected-email guardrails, and Gmail-safe actions.
          </p>
        </div>
        <div className="workspace-bar-tools">
          <div className="stat-chip">
            <span>Total</span>
            <strong>{formatCount(emails.length)}</strong>
          </div>
          <div className="stat-chip">
            <span>Connected</span>
            <strong>{auth?.gmail_account ? "Yes" : "No"}</strong>
          </div>
        </div>
      </header>

      {error ? <div className="alert error">{error}</div> : null}
      {notice ? <div className="alert success">{notice}</div> : null}

      <div className="workspace-grid">
        <aside className="panel inbox-column">
          <div className="inbox-column-head">
            <div>
              <p className="eyebrow">Mailbox</p>
              <h2>Queue</h2>
            </div>
            {auth?.user ? <span className="status-dot online">Live</span> : null}
          </div>

          {auth?.user ? (
            <div className="account-panel">
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
              <div className="button-stack compact">
                <button onClick={syncEmails} disabled={syncing}>
                  {syncing ? "Syncing..." : "Sync inbox"}
                </button>
                <button className="secondary" onClick={reviewArchiveCandidates} disabled={archiveReviewLoading}>
                  {archiveReviewLoading ? "Loading..." : "Review & Archive"}
                </button>
                <button className="secondary" onClick={useDemoInbox} disabled={demoLoading}>
                  {demoLoading ? <span className="button-loading" /> : null}
                  {demoLoading ? "Preparing demo" : "Load demo inbox"}
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
            </div>
          ) : (
            <div className="account-panel">
              <p className="muted">Connect Google to sync and act on real Gmail messages.</p>
              <div className="button-stack compact">
                <button onClick={startGoogleLogin}>Sign in with Google</button>
                <button className="secondary" onClick={useDemoInbox} disabled={demoLoading}>
                  {demoLoading ? <span className="button-loading" /> : null}
                  {demoLoading ? "Preparing demo" : "Use demo inbox"}
                </button>
              </div>
            </div>
          )}

          <div className="inbox-list-head">
            <p className="eyebrow">Emails</p>
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
        </aside>

        <main className="reader-column">
          {!selectedEmail ? (
            <div className="panel empty-state">
              <h2>No email selected</h2>
              <p>Connect Gmail or load the demo inbox to start reviewing recommendations.</p>
            </div>
          ) : (
            <>
              <section className="panel reader-hero">
                <div>
                  <p className="eyebrow">Selected Email</p>
                  <h2>{selectedEmail.subject || "(No subject)"}</h2>
                  <div className="sender-meta">
                    <strong>{selectedSender}</strong>
                    <span className="dot-separator" />
                    <span className="muted">{selectedEmail.sender_email || "Unknown sender"}</span>
                  </div>
                </div>
                <div className="reader-hero-meta">
                  <span className="status-pill">{selectedEmail.is_read ? "Read" : "Unread"}</span>
                  <span className="tone-pill neutral">{selectedSource}</span>
                  <time>{formatDetailDate(selectedEmail.received_at || selectedEmail.created_at)}</time>
                </div>
              </section>

              <section className="panel reader-body">
                <div className="reader-toolbar">
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

                <div className="reader-sections">
                  <section className="reader-block preview-block">
                    <p className="eyebrow">Preview</p>
                    <p className="message-snippet">{selectedEmail.snippet || "No preview available."}</p>
                  </section>

                  <section className="reader-block message-block">
                    <p className="eyebrow">Message</p>
                    <div className="message-copy">
                      {selectedParagraphs.length > 0 ? (
                        selectedParagraphs.map((paragraph, index) => <p key={index}>{paragraph}</p>)
                      ) : (
                        <p>No body text captured.</p>
                      )}
                    </div>
                  </section>
                </div>
              </section>

              <section className="panel context-panel">
                <div className="panel-header">
                  <div>
                    <p className="eyebrow">Context</p>
                    <h2>Similar emails</h2>
                  </div>
                  <span className="count-pill">{similarEmails.length}</span>
                </div>
                {similarEmails.length === 0 ? <p className="muted">No similar emails yet.</p> : null}
                <div className="similar-grid">
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
              </section>
            </>
          )}
        </main>

        <aside className="decision-column">
          {selectedEmail ? (
            <>
              <div className={`panel recommendation-panel recommendation-panel-${getTone(selectedEmail.classification?.suggested_action)}`}>
                <div className="recommendation-header">
                  <div>
                    <p className="eyebrow">Recommendation</p>
                    <h2>{selectedEmail.classification?.suggested_action || "review"}</h2>
                  </div>
                  <span className="tone-pill neutral">
                    {formatRecommendationSource(selectedEmail.classification?.source)}
                  </span>
                </div>
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
                <p className="eyebrow">Actions</p>
                <h2>Apply cleanup</h2>
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
            </>
          ) : null}
        </aside>
      </div>
      {archiveReviewOpen ? (
        <div className="modal-backdrop" onClick={exitArchiveReview}>
          <div className="modal-card" onClick={(event) => event.stopPropagation()}>
            <div className="modal-header">
              <div>
                <p className="eyebrow">Archive Review</p>
                <h2>Review these emails before archiving</h2>
              </div>
              <span className="count-pill">{archiveCandidates.length}</span>
            </div>
            <div className="modal-list">
              {archiveCandidates.map((email) => (
                <button
                  key={email.id}
                  className={`modal-email-card ${selectedEmail?.id === email.id ? "active" : ""}`}
                  onClick={() => loadEmailDetail(email.id)}
                >
                  <div className="modal-email-row">
                    <strong>{email.subject || "(No subject)"}</strong>
                    <time>{formatListDate(email.received_at || email.created_at)}</time>
                  </div>
                  <p>{email.sender_name || email.sender_email || "Unknown sender"}</p>
                  <span>{clampText(email.snippet || "No preview available.", 120)}</span>
                </button>
              ))}
            </div>
            <div className="modal-actions">
              <button
                onClick={confirmArchiveCandidates}
                disabled={archiveConfirming || archiveCandidates.length === 0}
              >
                {archiveConfirming ? "Archiving reviewed emails..." : "Archive these emails"}
              </button>
              <button className="secondary" onClick={exitArchiveReview}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
