import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowDownLeft,
  ArrowRight,
  ArrowUpRight,
  BadgeCheck,
  Bike,
  CalendarDays,
  Check,
  ChevronDown,
  CircleHelp,
  Clock3,
  IndianRupee,
  LayoutDashboard,
  LogOut,
  Mail,
  MapPin,
  PackageCheck,
  PackageOpen,
  ShieldCheck,
  Sparkles,
  UsersRound,
} from "lucide-react";

let csrfToken = "";

async function api(path, options = {}) {
  const headers = { ...(options.body ? { "Content-Type": "application/json" } : {}), ...options.headers };
  if (options.method && options.method !== "GET" && csrfToken) {
    headers["X-CSRF-Token"] = csrfToken;
  }
  const response = await fetch(`/api${path}`, { ...options, headers });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && path !== "/auth/login") {
      throw new Error("Your session has expired. Please sign in again.");
    }
    throw new Error(payload.error || "Something went wrong. Please try again.");
  }
  if (payload.csrf_token) csrfToken = payload.csrf_token;
  return payload;
}

const currency = (value) =>
  new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value || 0);

const longDate = new Intl.DateTimeFormat("en-IN", {
  weekday: "long",
  day: "numeric",
  month: "long",
  year: "numeric",
});

function localDateString(value = new Date()) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function shortDate(value) {
  return new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short" }).format(
    new Date(`${value}T00:00:00`),
  );
}

function time(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-IN", { hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const refreshSession = useCallback(async () => {
    try {
      await api("/auth/csrf");
      const { user: current } = await api("/auth/me");
      setUser(current);
    } catch (requestError) {
      setUser(null);
      if (!requestError.message.includes("session has expired") && !requestError.message.includes("sign in to continue")) {
        setError(requestError.message);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshSession();
  }, [refreshSession]);

  async function signOut() {
    setError("");
    try {
      await api("/auth/logout", { method: "POST" });
      setUser(null);
      setNotice("You’ve been signed out.");
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  if (loading) return <div className="loading-screen"><span className="loader" /> Getting your workspace ready</div>;
  if (!user) {
    return (
      <AuthScreen
        onAuthenticated={setUser}
        error={error}
        setError={setError}
        notice={notice}
        setNotice={setNotice}
      />
    );
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#" aria-label="Relay home">
          <span className="brand-mark"><Bike size={21} strokeWidth={2.4} /></span>
          <span>relay<span className="brand-period">.</span></span>
        </a>
        <div className="workspace-label">WORKSPACE</div>
        <nav className="side-nav" aria-label="Main navigation">
          <a href="#overview" className="nav-link active"><LayoutDashboard size={18} /> Overview</a>
          <a href="#history" className="nav-link"><CalendarDays size={18} /> {user.role === "admin" ? "Reports" : "Attendance"}</a>
        </nav>
        <div className="sidebar-bottom">
          <div className="help-card">
            <span className="help-icon"><CircleHelp size={17} /></span>
            <div><strong>Need a hand?</strong><span>Your team is here for you.</span></div>
            <ArrowRight size={15} />
          </div>
          <div className="sidebar-user">
            <div className="avatar">{user.full_name.charAt(0).toUpperCase()}</div>
            <div className="user-meta"><strong>{user.full_name}</strong><span>{user.role === "admin" ? "Administrator" : "Delivery partner"}</span></div>
            <button className="icon-button signout" onClick={signOut} aria-label="Sign out" title="Sign out"><LogOut size={17} /></button>
          </div>
        </div>
      </aside>
      <main className="main-area">
        <header className="topbar">
          <div className="breadcrumbs"><span>Workspace</span><span className="crumb-slash">/</span><strong>{user.role === "admin" ? "Operations" : "My overview"}</strong></div>
          <div className="topbar-right">
            <span className="top-date"><CalendarDays size={15} /> {longDate.format(new Date())}</span>
            <span className="top-avatar">{user.full_name.charAt(0).toUpperCase()}</span>
          </div>
        </header>
        <section className="page-content" id="overview">
          {error && <Alert message={error} onDismiss={() => setError("")} />}
          {notice && <Alert message={notice} success onDismiss={() => setNotice("")} />}
          {user.role === "admin" ? (
            <AdminDashboard setError={setError} />
          ) : (
            <PartnerDashboard user={user} setError={setError} />
          )}
        </section>
        <footer className="page-footer"><span>© {new Date().getFullYear()} Relay Logistics</span><span><ShieldCheck size={14} /> Your information is securely protected</span></footer>
      </main>
    </div>
  );
}

function Alert({ message, success, onDismiss }) {
  return (
    <div className={`alert ${success ? "alert-success" : "alert-error"}`} role={success ? "status" : "alert"}>
      <span>{success ? <Check size={16} /> : <CircleHelp size={16} />}</span>
      <p>{message}</p>
      <button className="alert-dismiss" onClick={onDismiss} aria-label="Dismiss message">×</button>
    </div>
  );
}

function AuthScreen({ onAuthenticated, error, setError, notice, setNotice }) {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ email: "", full_name: "", password: "", confirm_password: "" });
  const [busy, setBusy] = useState(false);
  const isRegister = mode === "register";

  async function submit(event) {
    event.preventDefault();
    if (isRegister && form.password !== form.confirm_password) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api("/auth/csrf");
      const result = await api(isRegister ? "/auth/register" : "/auth/login", {
        method: "POST",
        body: JSON.stringify(form),
      });
      if (isRegister) {
        setMode("login");
        setForm({ email: result.email, full_name: "", password: "", confirm_password: "" });
        setNotice(result.message);
      } else {
        onAuthenticated(result.user);
      }
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-screen">
      <section className="auth-aside">
        <a className="brand brand-light" href="#"><span className="brand-mark"><Bike size={21} strokeWidth={2.4} /></span><span>relay<span className="brand-period">.</span></span></a>
        <div className="auth-promo">
          <div className="eyebrow"><Sparkles size={14} /> YOUR WORK, REWARDED</div>
          <h1>Every mile<br />moves you <em>forward.</em></h1>
          <p>Your workday, your earnings, all in one place. Check in, deliver, and watch your hard work add up.</p>
          <div className="promo-stat"><span className="promo-stat-icon"><IndianRupee size={20} /></span><div><strong>₹15</strong><span>for every completed delivery</span></div><ArrowUpRight size={18} /></div>
        </div>
        <div className="auth-aside-footer"><span>Built for the people who keep us moving.</span><span>01 — 03</span></div>
        <div className="decor-circle decor-one" /><div className="decor-circle decor-two" />
      </section>
      <section className="auth-main">
        <div className="auth-form-wrap">
          <div className="mobile-auth-brand"><span className="brand-mark"><Bike size={20} /></span> relay<span className="brand-period">.</span></div>
          <div className="auth-heading">
            <div className="eyebrow dark-eyebrow">{isRegister ? "JOIN YOUR TEAM" : "WELCOME BACK"}</div>
            <h2>{isRegister ? "Create your account" : "Good to see you."}</h2>
            <p>{isRegister ? "Set up your delivery partner profile to get started." : "Sign in to pick up right where you left off."}</p>
          </div>
          {error && <Alert message={error} onDismiss={() => setError("")} />}
          {notice && <Alert message={notice} success onDismiss={() => setNotice("")} />}
          <form className="auth-form" onSubmit={submit}>
            {isRegister && <label>Your full name<input autoComplete="name" required maxLength={100} placeholder="e.g. Arjun Sharma" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></label>}
            <label>Email address<div className="input-with-icon"><Mail size={17} /><input type={isRegister ? "email" : "text"} inputMode="email" autoComplete="email" required maxLength={254} placeholder={isRegister ? "you@example.com" : "Enter your email address"} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></div></label>
            {!isRegister && <span className="legacy-login-hint">Existing accounts can still sign in with their username.</span>}
            <label>{isRegister ? "Create password" : "Password"}<div className="input-with-icon"><ShieldCheck size={17} /><input autoComplete={isRegister ? "new-password" : "current-password"} required minLength={isRegister ? 10 : 1} maxLength={128} type="password" placeholder={isRegister ? "At least 10 characters" : "Enter your password"} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></div></label>
            {isRegister && <label>Confirm password<div className="input-with-icon"><ShieldCheck size={17} /><input autoComplete="new-password" required minLength={10} maxLength={128} type="password" placeholder="Enter your password again" value={form.confirm_password} onChange={(e) => setForm({ ...form, confirm_password: e.target.value })} /></div></label>}
            <button className="button button-primary auth-submit" disabled={busy}>{busy ? "Please wait…" : isRegister ? "Create account" : "Sign in"} <ArrowRight size={17} /></button>
          </form>
          <div className="auth-switch">{isRegister ? "Already part of the team?" : "New to the team?"} <button onClick={() => { setMode(isRegister ? "login" : "register"); setForm({ ...form, password: "", confirm_password: "" }); setError(""); setNotice(""); }}> {isRegister ? "Sign in" : "Create an account"}</button></div>
          <div className="auth-security"><ShieldCheck size={15} /> Your account and earnings are always private.</div>
        </div>
      </section>
    </main>
  );
}

function PartnerDashboard({ user, setError }) {
  const [data, setData] = useState(null);
  const [counts, setCounts] = useState({ pickup_count: "0", completed_count: "0" });
  const [busy, setBusy] = useState(false);
  const [historyHasMore, setHistoryHasMore] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);

  const load = useCallback(async () => {
    try {
      const result = await api("/dashboard");
      setData(result);
      setCounts({
        pickup_count: String(result.today?.pickup_count ?? 0),
        completed_count: String(result.today?.completed_count ?? 0),
      });
      setHistoryHasMore(result.history_has_more);
    } catch (requestError) {
      setError(requestError.message);
    }
  }, [setError]);

  useEffect(() => { load(); }, [load]);

  async function attendanceAction(action) {
    setBusy(true);
    setError("");
    try {
      await api(`/attendance/${action}`, { method: "POST" });
      await load();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  async function saveCounts(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/attendance/today", {
        method: "PUT",
        body: JSON.stringify({
          pickup_count: Number(counts.pickup_count),
          completed_count: Number(counts.completed_count),
        }),
      });
      await load();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  async function loadMoreHistory() {
    setHistoryLoading(true);
    setError("");
    try {
      const result = await api(`/attendance/history?limit=20&offset=${data.history.length}`);
      setData((current) => ({ ...current, history: [...current.history, ...result.history] }));
      setHistoryHasMore(result.has_more);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setHistoryLoading(false);
    }
  }

  if (!data) return <div className="content-loading"><span className="loader" /> Loading your dashboard</div>;
  const today = data.today;
  const checkedIn = Boolean(today);
  const checkedOut = Boolean(today?.check_out);

  return (
    <>
      <div className="page-heading">
        <div><div className="eyebrow dark-eyebrow">YOUR DELIVERY DESK</div><h1>Hey, {user.full_name.split(" ")[0]} <span className="wave">✳</span></h1><p>Here’s what’s happening with your deliveries today.</p></div>
        <div className="rate-pill"><span><IndianRupee size={14} /></span> ₹{data.rate_per_delivery} <small>per completed delivery</small></div>
      </div>
      <div className="partner-stats">
        <StatCard title="EARNED TODAY" value={currency(data.today_earnings)} icon={IndianRupee} accent="orange" caption={today ? `${today.completed_count} completed deliveries` : "Start your shift to begin"} />
        <StatCard title="LIFETIME EARNINGS" value={currency(data.lifetime_earnings)} icon={ArrowUpRight} accent="green" caption="Across all your delivery days" />
        <StatCard title="COMPLETED DELIVERIES" value={data.lifetime_completed} icon={PackageCheck} accent="blue" caption={`${data.lifetime_pickups} pickups collected`} />
        <StatCard title="DAYS ON THE ROAD" value={data.attendance_days} icon={CalendarDays} accent="violet" caption="Days you’ve checked in" />
      </div>
      <div className="partner-grid">
        <section className="panel shift-panel">
          <div className="panel-heading"><div><span className="section-kicker">TODAY’S SHIFT</span><h2>Attendance</h2></div><span className={`status-badge ${checkedOut ? "status-muted" : checkedIn ? "status-live" : "status-muted"}`}><span />{checkedOut ? "Shift complete" : checkedIn ? "On shift" : "Not checked in"}</span></div>
          <div className="shift-timeline">
            <div className={`timeline-mark ${checkedIn ? "mark-done" : ""}`}>{checkedIn ? <Check size={15} /> : <MapPin size={15} />}</div>
            <div className="timeline-info"><strong>Check in</strong><span>{checkedIn ? `You started at ${time(today.check_in)}` : "Record your arrival to start your day"}</span></div>
            <span className="timeline-time">{checkedIn ? time(today.check_in) : "—"}</span>
          </div>
          <div className="timeline-connector" />
          <div className="shift-timeline">
            <div className={`timeline-mark ${checkedOut ? "mark-done" : "mark-pending"}`}>{checkedOut ? <Check size={15} /> : <MapPin size={15} />}</div>
            <div className="timeline-info"><strong>Check out</strong><span>{checkedOut ? `You wrapped up at ${time(today.check_out)}` : checkedIn ? "Finish your shift when you’re all done" : "Waiting for your check-in"}</span></div>
            <span className="timeline-time">{checkedOut ? time(today.check_out) : "—"}</span>
          </div>
          <div className="shift-footer">
            {!checkedIn ? <button className="button button-primary" disabled={busy} onClick={() => attendanceAction("check-in")}><MapPin size={17} /> Check in for today <ArrowRight size={16} /></button> :
              !checkedOut ? <button className="button button-outline" disabled={busy} onClick={() => attendanceAction("check-out")}><Check size={17} /> Check out for today</button> :
                <div className="shift-complete"><BadgeCheck size={17} /> Nice work today. See you next shift!</div>}
            <span>Today · {shortDate(localDateString())}</span>
          </div>
        </section>
        <section className="panel delivery-panel">
          <div className="panel-heading"><div><span className="section-kicker">KEEP YOUR DAY UPDATED</span><h2>Delivery totals</h2></div><span className="delivery-emoji"><PackageOpen size={19} /></span></div>
          <form onSubmit={saveCounts}>
            <div className="count-fields">
              <label><span>Pickups collected</span><div className="number-input"><ArrowDownLeft size={16} /><input aria-label="Pickups collected" type="number" inputMode="numeric" min="0" max="10000" step="1" value={counts.pickup_count} onChange={(e) => setCounts({ ...counts, pickup_count: e.target.value })} disabled={!checkedIn || checkedOut} required /></div></label>
              <label><span>Deliveries completed</span><div className="number-input completed-input"><PackageCheck size={16} /><input aria-label="Deliveries completed" type="number" inputMode="numeric" min="0" max="10000" step="1" value={counts.completed_count} onChange={(e) => setCounts({ ...counts, completed_count: e.target.value })} disabled={!checkedIn || checkedOut} required /></div></label>
            </div>
            <div className="earnings-preview"><div><span>Today’s earnings</span><small>Only completed deliveries count</small></div><strong>{currency((Number(counts.completed_count) || 0) * data.rate_per_delivery)}</strong></div>
            <button className="button button-dark delivery-save" disabled={busy || !checkedIn || checkedOut}><Check size={16} /> {checkedOut ? "Shift totals locked" : checkedIn ? "Save today’s totals" : "Check in to get started"}</button>
          </form>
        </section>
      </div>
      <HistoryPanel history={data.history} hasMore={historyHasMore} loadingMore={historyLoading} onLoadMore={loadMoreHistory} />
    </>
  );
}

function StatCard({ title, value, icon: Icon, accent, caption }) {
  return <article className="stat-card"><div className={`stat-icon stat-${accent}`}><Icon size={18} /></div><span className="stat-title">{title}</span><strong className="stat-value">{value}</strong><span className="stat-caption">{caption}</span></article>;
}

function HistoryPanel({ history, hasMore = false, loadingMore = false, onLoadMore }) {
  return (
    <section className="panel history-panel" id="history">
      <div className="panel-heading history-heading"><div><span className="section-kicker">YOUR RECENT ACTIVITY</span><h2>Attendance history</h2></div><span className="history-count">{history.length} {history.length === 1 ? "day" : "days"}</span></div>
      {history.length ? <><div className="table-scroll"><table><thead><tr><th>DATE</th><th>CHECK IN</th><th>CHECK OUT</th><th>PICKUPS</th><th>COMPLETED</th><th className="align-right">EARNED</th></tr></thead><tbody>{history.map((day) => <tr key={day.id}><td><strong>{shortDate(day.date)}</strong><span className="table-sub">{day.date === localDateString() ? "Today" : new Intl.DateTimeFormat("en-IN", { weekday: "short" }).format(new Date(`${day.date}T00:00:00`))}</span></td><td>{time(day.check_in)}</td><td>{time(day.check_out)}</td><td>{day.pickup_count}</td><td><span className="completed-cell"><PackageCheck size={14} /> {day.completed_count}</span></td><td className="align-right amount-cell">{currency(day.earnings)}</td></tr>)}</tbody></table></div>{hasMore && onLoadMore && <button className="load-more" onClick={onLoadMore} disabled={loadingMore}>{loadingMore ? "Loading earlier days…" : "Load earlier attendance"} <ArrowRight size={14} /></button>}</> : <EmptyState icon={Clock3} title="Your story starts here" text="Check in for your first shift and your attendance history will show up here." />}
    </section>
  );
}

function AdminDashboard({ setError }) {
  const todayString = localDateString();
  const monthStart = `${todayString.slice(0, 7)}-01`;
  const [range, setRange] = useState({ from: monthStart, to: todayString });
  const [report, setReport] = useState(null);
  const [selectedPartner, setSelectedPartner] = useState("");
  const [individual, setIndividual] = useState(null);
  const [busy, setBusy] = useState(false);

  const rangeQuery = useMemo(() => `from=${encodeURIComponent(range.from)}&to=${encodeURIComponent(range.to)}`, [range]);
  const loadReport = useCallback(async () => {
    setBusy(true);
    try {
      const result = await api(`/admin/reports?${rangeQuery}`);
      setReport(result);
      setSelectedPartner((current) => result.partners.some((partner) => String(partner.id) === current) ? current : "");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }, [rangeQuery, setError]);

  useEffect(() => { loadReport(); }, [loadReport]);

  useEffect(() => {
    if (!selectedPartner) {
      setIndividual(null);
      return;
    }
    let active = true;
    api(`/admin/reports/${selectedPartner}?${rangeQuery}`)
      .then((result) => { if (active) setIndividual(result); })
      .catch((requestError) => { if (active) setError(requestError.message); });
    return () => { active = false; };
  }, [rangeQuery, selectedPartner, setError]);

  if (!report) return <div className="content-loading"><span className="loader" /> Loading operations report</div>;
  const stats = report.summary;
  const maxDaily = Math.max(1, ...report.daily.map((day) => day.completed_count));
  const partnerView = selectedPartner ? individual : null;

  return (
    <>
      <div className="page-heading admin-page-heading">
        <div><div className="eyebrow dark-eyebrow">OPERATIONS OVERVIEW</div><h1>Good morning<span className="wave">✳</span></h1><p>Here’s how your delivery team is performing.</p></div>
        <div className="report-controls"><label>From<input type="date" value={range.from} max={range.to} onChange={(e) => setRange({ ...range, from: e.target.value })} /></label><ArrowRight size={15} /><label>To<input type="date" value={range.to} min={range.from} max={todayString} onChange={(e) => setRange({ ...range, to: e.target.value })} /></label></div>
      </div>
      <div className="admin-stats">
        <StatCard title="TOTAL EARNINGS" value={currency(stats.earnings)} icon={IndianRupee} accent="orange" caption="Based on completed deliveries" />
        <StatCard title="COMPLETED DELIVERIES" value={stats.completed_count} icon={PackageCheck} accent="green" caption={`${stats.pickup_count} pickups collected`} />
        <StatCard title="ATTENDANCE DAYS" value={stats.attendance_days} icon={CalendarDays} accent="blue" caption="Across all delivery partners" />
        <StatCard title="REGISTERED PARTNERS" value={stats.partner_count} icon={UsersRound} accent="violet" caption="Registered delivery partners" />
      </div>
      <section className="panel performance-panel">
        <div className="panel-heading"><div><span className="section-kicker">TEAM PERFORMANCE</span><h2>Delivery activity</h2></div><span className="chart-legend"><i /> Completed deliveries</span></div>
        {report.daily.length ? <div className="chart-wrap"><div className="chart-y-labels"><span>{maxDaily}</span><span>{Math.round(maxDaily / 2)}</span><span>0</span></div><div className="bar-chart">{report.daily.map((day) => <div className="bar-column" key={day.date}><div className="bar-track"><div className="bar-fill" style={{ height: `${Math.max(4, (day.completed_count / maxDaily) * 100)}%` }} title={`${day.completed_count} completed`} /></div><span>{shortDate(day.date)}</span></div>)}</div></div> : <EmptyState icon={PackageCheck} title="No delivery activity yet" text="Completed deliveries will appear here once your team starts recording shifts." />}
      </section>
      <section className="panel history-panel report-panel" id="history">
        <div className="panel-heading history-heading"><div><span className="section-kicker">PARTNER BREAKDOWN</span><h2>Individual reports</h2></div><span className="history-count">{report.partners.length} {report.partners.length === 1 ? "partner" : "partners"}</span></div>
        {report.partners.length ? <div className="table-scroll"><table><thead><tr><th>DELIVERY PARTNER</th><th>ATTENDANCE</th><th>PICKUPS</th><th>COMPLETED</th><th className="align-right">EARNINGS</th></tr></thead><tbody>{report.partners.map((partner) => <tr key={partner.id} className={selectedPartner === String(partner.id) ? "selected-row" : ""} onClick={() => setSelectedPartner(selectedPartner === String(partner.id) ? "" : String(partner.id))} tabIndex={0} onKeyDown={(event) => { if (event.key === "Enter") setSelectedPartner(String(partner.id)); }}><td><span className="partner-cell-avatar">{partner.full_name.charAt(0).toUpperCase()}</span><span className="partner-name">{partner.full_name}<small>{partner.email || `Legacy account · ${partner.legacy_username}`}</small></span></td><td>{partner.attendance_days} {partner.attendance_days === 1 ? "day" : "days"}</td><td>{partner.pickup_count}</td><td><span className="completed-cell"><PackageCheck size={14} /> {partner.completed_count}</span></td><td className="align-right amount-cell">{currency(partner.earnings)}</td></tr>)}</tbody></table></div> : <EmptyState icon={UsersRound} title="No partners on your team yet" text="Delivery partners can create an account from the sign-in page." />}
      </section>
      {partnerView && <section className="panel individual-panel"><div className="panel-heading"><div><span className="section-kicker">INDIVIDUAL REPORT</span><h2>{partnerView.partner.full_name}</h2></div><button className="text-button" onClick={() => setSelectedPartner("")}>Close report ×</button></div><div className="individual-metrics"><div><span>ATTENDANCE</span><strong>{partnerView.summary.attendance_days} {partnerView.summary.attendance_days === 1 ? "day" : "days"}</strong></div><div><span>COMPLETED</span><strong>{partnerView.summary.completed_count}</strong></div><div><span>PICKUPS</span><strong>{partnerView.summary.pickup_count}</strong></div><div><span>EARNINGS</span><strong>{currency(partnerView.summary.earnings)}</strong></div></div><HistoryPanel history={partnerView.history} /></section>}
      {busy && <span className="refresh-indicator"><span className="loader small-loader" /> Updating report</span>}
    </>
  );
}

function EmptyState({ icon: Icon, title, text }) {
  return <div className="empty-state"><span className="empty-icon"><Icon size={22} /></span><strong>{title}</strong><p>{text}</p></div>;
}

export default App;
