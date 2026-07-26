import { useState, useRef, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Send, Zap, Database, FileText, ChevronDown, ChevronUp,
  Bot, User, Loader2, RotateCcw, AlertTriangle, CheckCircle2,
  Copy, Check, TrendingUp, Building2, ClipboardList, ShieldAlert,
} from "lucide-react";

// ── types ─────────────────────────────────────────────────────────────────────

interface ToolCall  { tool: string; input: Record<string, unknown>; result: string }
interface TraceItem { id: string; tool: string; input: Record<string, unknown>; status: "running" | "done" }

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  tool_calls?: ToolCall[];
  sources?: string[];
  trace?: TraceItem[];
  error?: boolean;
  streaming?: boolean;
}

interface Stats {
  active_vendors: number;
  active_contracts: number;
  ytd_spend: number;
  open_pos: number;
  anomalies: number;
}

// ── constants ─────────────────────────────────────────────────────────────────

const SUGGESTED = [
  { label: "Top vendors by spend",         q: "Who are our top 10 vendors by year-to-date spend?" },
  { label: "Contracts expiring soon",       q: "Which active contracts expire in the next 90 days, and do any auto-renew?" },
  { label: "Payment term mismatches",       q: "Find invoices whose payment terms are shorter than what the underlying contract specifies." },
  { label: "Split PO detection",            q: "Are there purchase orders that look like they were split to stay under approval thresholds?" },
  { label: "Spend without a contract",      q: "Which vendors have more than $50,000 in YTD spend but no active contract?" },
  { label: "Contract cap breaches",         q: "Flag contracts where cumulative invoice spend has exceeded the stated value cap." },
  { label: "Orion Logistics auto-renew",    q: "Summarize the auto-renewal and notice period terms in the Orion Logistics contract." },
  { label: "PO splitting policy",           q: "What does the procurement policy say about splitting purchase orders?" },
  { label: "Stratos Cloud spend",           q: "What is our total spend with Stratos Cloud Services over the last 12 months?" },
  { label: "Renegotiation brief",           q: "Draft a one-paragraph renegotiation brief for the three vendors where we have the most leverage." },
];

// ── utility hooks ─────────────────────────────────────────────────────────────

function useCounter(target: number, duration = 1400) {
  const [val, setVal] = useState(0);
  useEffect(() => {
    if (!target) return;
    let raf: number;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min((now - start) / duration, 1);
      const ease = 1 - Math.pow(1 - t, 3);
      setVal(Math.round(target * ease));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, duration]);
  return val;
}

function useCopy(text: string) {
  const [copied, setCopied] = useState(false);
  const copy = useCallback(() => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [text]);
  return { copied, copy };
}

function fmtCurrency(n: number) {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `$${Math.round(n / 1_000)}K`;
  return `$${Math.round(n)}`;
}

// ── sub-components ────────────────────────────────────────────────────────────

function KPITile({
  label, raw, formatted, Icon, accent,
}: { label: string; raw: number; formatted?: string; Icon: React.ElementType; accent: string }) {
  const counted = useCounter(raw);
  const display = formatted
    ? fmtCurrency(raw === 0 ? 0 : (raw * counted) / raw)
    : counted.toLocaleString();

  return (
    <div className="glass-card rounded-2xl p-4 flex flex-col gap-2 animate-fade-slide-up">
      <div className={`w-8 h-8 rounded-xl flex items-center justify-center ${accent}`}>
        <Icon size={15} className="text-white" />
      </div>
      <p className="text-2xl font-bold text-slate-800 tracking-tight">{display}</p>
      <p className="text-xs text-slate-500 leading-tight">{label}</p>
    </div>
  );
}

function WelcomeScreen({ stats, onQuestion }: { stats: Stats | null; onQuestion: (q: string) => void }) {
  return (
    <div className="flex-1 overflow-y-auto flex flex-col items-center justify-start pt-10 px-8 pb-4">
      {/* Hero */}
      <div className="text-center mb-8 animate-fade-slide-up">
        <div className="w-16 h-16 logo-gradient rounded-2xl flex items-center justify-center mx-auto mb-4 shadow-lg shadow-red-300/50">
          <span className="text-white font-extrabold text-xl tracking-tight">DB</span>
        </div>
        <h1 className="text-3xl font-bold gradient-text mb-2">Data-bot</h1>
        <p className="text-slate-500 text-sm max-w-md">
          Your AI procurement copilot — ask anything across vendors, contracts,
          purchase orders, invoices, and policy documents.
        </p>
      </div>

      {/* KPI tiles */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 w-full max-w-2xl mb-8">
        {stats ? (
          <>
            <KPITile label="Active Vendors"    raw={stats.active_vendors}   Icon={Building2}     accent="bg-blue-600" />
            <KPITile label="Active Contracts"  raw={stats.active_contracts} Icon={FileText}      accent="bg-red-600" />
            <KPITile label="YTD Spend (USD)"   raw={stats.ytd_spend}        formatted="currency" Icon={TrendingUp}     accent="bg-emerald-600" />
            <KPITile label="Open POs"          raw={stats.open_pos}         Icon={ClipboardList} accent="bg-amber-600" />
          </>
        ) : (
          Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="glass-card rounded-2xl p-4 h-24 shimmer" />
          ))
        )}
      </div>

      {stats && stats.anomalies > 0 && (
        <div className="flex items-center gap-2 text-amber-700 text-xs bg-amber-50 border border-amber-200 rounded-xl px-4 py-2 mb-6 animate-fade-in">
          <ShieldAlert size={13} />
          <span><strong>{stats.anomalies}</strong> payment-term anomalies detected in your invoice data. Try <em>"Find invoices with mismatched payment terms"</em></span>
        </div>
      )}

      {/* Suggested questions */}
      <div className="w-full max-w-2xl">
        <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-widest mb-3">Try asking</p>
        <div className="grid grid-cols-2 gap-2">
          {SUGGESTED.slice(0, 8).map((s, i) => (
            <button
              key={i}
              onClick={() => onQuestion(s.q)}
              className="text-left text-xs text-slate-600 hover:text-red-700 glass-card hover:border-red-300 rounded-xl px-3.5 py-2.5 transition-all duration-200 hover:bg-red-50/60 animate-fade-slide-up"
              style={{ animationDelay: `${i * 40}ms` }}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function AgentTrace({ trace }: { trace: TraceItem[] }) {
  return (
    <div className="space-y-1.5 mb-3">
      {trace.map((item, i) => (
        <div
          key={item.id}
          className={`flex items-center gap-2 text-[11px] px-3 py-1.5 rounded-lg animate-fade-slide-left ${
            item.status === "running"
              ? "bg-red-50 border border-red-200 text-red-700"
              : "bg-slate-50 border border-slate-200 text-slate-500"
          }`}
          style={{ animationDelay: `${i * 60}ms` }}
        >
          {item.status === "running" ? (
            <Loader2 size={10} className="animate-spin flex-shrink-0 text-red-500" />
          ) : (
            <CheckCircle2 size={10} className="flex-shrink-0 text-emerald-500" />
          )}
          <span className="font-medium">
            {item.tool === "query_database" ? "Querying database" : "Searching documents"}
          </span>
          <span className="text-slate-300">·</span>
          <span className="font-mono opacity-60 truncate max-w-[240px]">
            {item.tool === "query_database"
              ? String(item.input.sql ?? "").slice(0, 55)
              : String(item.input.query ?? "").slice(0, 55)}
          </span>
        </div>
      ))}
    </div>
  );
}

function ToolDrawer({ toolCalls }: { toolCalls: ToolCall[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-3 rounded-xl border border-slate-200 overflow-hidden text-xs">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-3 py-2 bg-red-50 hover:bg-red-100 text-red-700 transition-colors"
      >
        <span className="flex items-center gap-1.5">
          <Zap size={10} className="text-red-600" />
          <span className="font-medium">{toolCalls.length} tool call{toolCalls.length !== 1 ? "s" : ""}</span>
        </span>
        {open ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
      </button>
      {open && (
        <div className="divide-y divide-slate-200">
          {toolCalls.map((tc, i) => (
            <div key={i} className="p-3 bg-white space-y-1.5">
              <div className="flex items-center gap-1.5">
                {tc.tool === "query_database"
                  ? <Database size={10} className="text-blue-500" />
                  : <FileText size={10} className="text-rose-500" />}
                <span className="font-mono font-semibold text-slate-600">{tc.tool}</span>
              </div>
              <pre className="text-[11px] text-slate-500 bg-slate-50 rounded-lg p-2 overflow-x-auto whitespace-pre-wrap leading-relaxed border border-slate-200">
                {tc.tool === "query_database"
                  ? String(tc.input.sql ?? "")
                  : String(tc.input.query ?? "")}
              </pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SourcePill({ source }: { source: string }) {
  const isDB = source === "Database";
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium border ${
      isDB
        ? "bg-blue-50 text-blue-700 border-blue-200"
        : "bg-rose-50 text-rose-700 border-rose-200"
    }`}>
      {isDB ? <Database size={9} /> : <FileText size={9} />}
      {source}
    </span>
  );
}

function CopyBtn({ text }: { text: string }) {
  const { copied, copy } = useCopy(text);
  return (
    <button
      onClick={copy}
      title="Copy response"
      className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-red-600 transition-all p-1 rounded"
    >
      {copied ? <Check size={12} className="text-emerald-500" /> : <Copy size={12} />}
    </button>
  );
}

function ChatBubble({ msg }: { msg: Message }) {
  if (msg.role === "user") {
    return (
      <div className="flex justify-end gap-2.5 mb-5 animate-fade-slide-up">
        <div className="max-w-[70%] bg-gradient-to-br from-red-600 to-red-700 text-white rounded-2xl rounded-tr-sm px-4 py-2.5 text-sm leading-relaxed shadow-lg shadow-red-200">
          {msg.content}
        </div>
        <div className="w-7 h-7 rounded-full bg-gradient-to-br from-red-600 to-red-700 flex items-center justify-center flex-shrink-0 mt-0.5 shadow">
          <User size={13} className="text-white" />
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start gap-2.5 mb-5 animate-fade-slide-up group">
      {/* Avatar */}
      <div className={`relative w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 shadow ${msg.streaming ? "thinking-ring" : ""} bg-gradient-to-br from-emerald-600 to-teal-600`}>
        {msg.streaming
          ? <Loader2 size={13} className="text-white animate-spin" />
          : <Bot size={13} className="text-white" />}
      </div>

      {/* Bubble */}
      <div className="min-w-0 flex-1 max-w-[92%] glass-card rounded-2xl rounded-tl-sm px-4 py-3 text-sm overflow-hidden">
        {msg.error ? (
          <div className="flex items-start gap-2 text-amber-700">
            <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" />
            <span>{msg.content}</span>
          </div>
        ) : (
          <>
            {/* Live agent trace (shown while streaming) */}
            {msg.trace && msg.trace.length > 0 && (
              <AgentTrace trace={msg.trace} />
            )}

            {/* Content */}
            {msg.content ? (
              <div className="prose prose-sm max-w-none prose-p:leading-relaxed prose-slate">
                <div className="overflow-x-auto">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                </div>
                {msg.streaming && <span className="cursor-blink" />}
              </div>
            ) : msg.streaming ? (
              <span className="text-slate-400 text-xs cursor-blink">Thinking</span>
            ) : null}

            {/* Footer: sources + copy + tool drawer */}
            {!msg.streaming && (
              <>
                {(msg.sources && msg.sources.length > 0) && (
                  <div className="flex flex-wrap items-center gap-1.5 mt-3 pt-3 border-t border-slate-200">
                    <span className="text-[11px] text-slate-400 mr-0.5">Sources</span>
                    {msg.sources.map((s, i) => <SourcePill key={i} source={s} />)}
                    <div className="ml-auto">
                      <CopyBtn text={msg.content} />
                    </div>
                  </div>
                )}
                {msg.tool_calls && msg.tool_calls.length > 0 && (
                  <ToolDrawer toolCalls={msg.tool_calls} />
                )}
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}

// ── main app ──────────────────────────────────────────────────────────────────

export default function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [stats, setStats]       = useState<Stats | null>(null);
  const [input, setInput]       = useState("");
  const [loading, setLoading]   = useState(false);
  const bottomRef               = useRef<HTMLDivElement>(null);
  const textareaRef             = useRef<HTMLTextAreaElement>(null);

  // Load KPI stats
  useEffect(() => {
    fetch("/api/stats").then(r => r.json()).then(setStats).catch(console.error);
  }, []);

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const autoResize = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 130) + "px";
  };

  const buildHistory = useCallback(() =>
    messages
      .filter(m => !m.streaming && m.role !== undefined)
      .map(m => ({ role: m.role, content: m.content })),
    [messages]
  );

  const send = useCallback(async (text?: string) => {
    const msg = (text ?? input).trim();
    if (!msg || loading) return;

    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";

    const userMsgId = crypto.randomUUID();
    const asstMsgId = crypto.randomUUID();
    const history = buildHistory();

    setMessages(prev => [
      ...prev,
      { id: userMsgId, role: "user", content: msg },
      { id: asstMsgId, role: "assistant", content: "", streaming: true, trace: [] },
    ]);
    setLoading(true);

    try {
      const res = await fetch("/api/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg, history }),
      });

      if (!res.ok) throw new Error(await res.text());

      const reader  = res.body!.getReader();
      const decoder = new TextDecoder();
      let   buffer  = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";

        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith("data: ")) continue;
          let event: Record<string, unknown>;
          try { event = JSON.parse(line.slice(6)); } catch { continue; }

          setMessages(prev => prev.map(m => {
            if (m.id !== asstMsgId) return m;

            switch (event.type) {
              case "tool_start":
                return {
                  ...m,
                  trace: [...(m.trace ?? []), {
                    id:     String(event.id ?? crypto.randomUUID()),
                    tool:   String(event.tool),
                    input:  (event.input as Record<string, unknown>) ?? {},
                    status: "running" as const,
                  }],
                };

              case "tool_end":
                return {
                  ...m,
                  trace: m.trace?.map(t =>
                    t.id === String(event.id) ? { ...t, status: "done" as const } : t
                  ),
                };

              case "text_delta":
                return { ...m, content: m.content + String(event.text ?? "") };

              case "done":
                return {
                  ...m,
                  streaming:  false,
                  tool_calls: (event.tool_calls as ToolCall[]) ?? [],
                  sources:    (event.sources as string[]) ?? [],
                };

              case "error":
                return { ...m, streaming: false, error: true, content: String(event.message ?? "Unknown error") };

              default:
                return m;
            }
          }));
        }
      }
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : "Unknown error";
      setMessages(prev => prev.map(m =>
        m.id === asstMsgId
          ? { ...m, streaming: false, error: true, content: `Connection error: ${errMsg}` }
          : m
      ));
    } finally {
      setLoading(false);
      textareaRef.current?.focus();
    }
  }, [input, loading, buildHistory]);

  const reset = () => { setMessages([]); setInput(""); };

  const showWelcome = messages.length === 0;

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: "linear-gradient(160deg, #f8f9fd 0%, #f1f2fa 100%)" }}>

      {/* ── sidebar ── */}
      <aside className="w-60 flex-shrink-0 sidebar-bg flex flex-col">
        {/* Logo */}
        <div className="px-4 py-4 border-b border-slate-200/70">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 logo-gradient rounded-xl flex items-center justify-center shadow shadow-red-200">
              <span className="text-white font-extrabold text-[10px] tracking-tight">DB</span>
            </div>
            <div>
              <p className="font-bold text-[15px] gradient-text leading-tight">Data-bot</p>
              <p className="text-[10px] text-slate-400">Procurement Copilot</p>
            </div>
          </div>
        </div>

        {/* Stack badge */}
        <div className="px-4 py-2.5 border-b border-slate-200/70">
          <div className="flex items-center gap-2 text-[10px] text-slate-500">
            <span className="flex items-center gap-1"><Database size={9} className="text-blue-500" /> SQLite</span>
            <span className="text-slate-300">·</span>
            <span className="flex items-center gap-1"><FileText size={9} className="text-rose-500" /> ChromaDB</span>
            <span className="text-slate-300">·</span>
            <span className="flex items-center gap-1"><Zap size={9} className="text-red-500" /> Claude</span>
          </div>
        </div>

        {/* Quick questions */}
        <div className="flex-1 overflow-y-auto py-3 px-2">
          <p className="text-[9px] font-bold text-slate-400 uppercase tracking-widest px-2 mb-2">Quick questions</p>
          {SUGGESTED.map((s, i) => (
            <button
              key={i}
              onClick={() => send(s.q)}
              disabled={loading}
              className="w-full text-left px-2.5 py-1.5 rounded-lg text-[11.5px] text-slate-500 hover:text-red-700 hover:bg-red-50 hover:border-red-200 border border-transparent transition-all duration-150 disabled:opacity-30 disabled:cursor-not-allowed leading-snug mb-0.5"
            >
              {s.label}
            </button>
          ))}
        </div>

        {/* Footer */}
        <div className="px-4 py-3 border-t border-slate-200/70 flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-[10px] text-slate-400">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
            2026-04-21
          </div>
          <button
            onClick={reset}
            title="New chat"
            className="text-slate-400 hover:text-red-600 transition-colors p-1 rounded hover:bg-red-50"
          >
            <RotateCcw size={12} />
          </button>
        </div>
      </aside>

      {/* ── main ── */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="px-6 py-3 border-b border-slate-200/70 flex-shrink-0 flex items-center justify-between"
          style={{ background: "rgba(255,255,255,0.85)", backdropFilter: "blur(12px)" }}>
          <div>
            <p className="font-semibold text-sm text-slate-700">Nimbus Retail Co.</p>
            <p className="text-[10px] text-slate-400">Finance & Procurement Intelligence</p>
          </div>
          {loading && (
            <div className="flex items-center gap-1.5 text-[11px] text-red-600 animate-fade-in">
              <Loader2 size={11} className="animate-spin" />
              <span>Agent running…</span>
            </div>
          )}
        </header>

        {/* Messages / Welcome */}
        {showWelcome ? (
          <WelcomeScreen stats={stats} onQuestion={send} />
        ) : (
          <div className="flex-1 overflow-y-auto px-6 py-5">
            {messages.map(msg => <ChatBubble key={msg.id} msg={msg} />)}
            <div ref={bottomRef} />
          </div>
        )}

        {/* Input bar */}
        <div className="px-6 pb-5 pt-3 border-t border-slate-200/70 flex-shrink-0"
          style={{ background: "rgba(255,255,255,0.85)", backdropFilter: "blur(12px)" }}>
          <div className="flex gap-3 items-end">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={e => { setInput(e.target.value); autoResize(); }}
              onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
              placeholder="Ask about vendors, contracts, spend, anomalies…"
              rows={1}
              disabled={loading}
              className="flex-1 rounded-xl px-4 py-3 text-sm text-slate-800 placeholder-slate-400 resize-none focus:outline-none transition-all leading-relaxed disabled:opacity-60"
              style={{
                minHeight: "48px",
                maxHeight: "130px",
                background: "#ffffff",
                border: "1px solid rgba(239,68,68,0.25)",
                boxShadow: input ? "0 0 0 3px rgba(239,68,68,0.12)" : "0 1px 2px rgba(15,23,42,0.04)",
              }}
            />
            <button
              onClick={() => send()}
              disabled={loading || !input.trim()}
              className="w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0 transition-all disabled:opacity-40 disabled:cursor-not-allowed shadow shadow-red-200"
              style={{ background: "linear-gradient(135deg, #ef4444, #dc2626)" }}
            >
              {loading
                ? <Loader2 size={15} className="animate-spin text-white/60" />
                : <Send size={15} className="text-white" />}
            </button>
          </div>
          <p className="text-[10px] text-slate-400 text-center mt-2">
            Enter to send · Shift+Enter for new line
          </p>
        </div>
      </div>
    </div>
  );
}
