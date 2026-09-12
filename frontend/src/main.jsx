import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { AreaChart, Area, BarChart, Bar, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { Bot, Database, Upload, Sparkles, Send, Table2, Trash2, Play, ChevronRight, ShieldCheck, BarChart3, Code2 } from 'lucide-react';
import './styles.css';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';
const EXAMPLES = ['Show total revenue by product', 'What is the average profit?', 'Show the top 5 products by revenue', 'Show revenue trend over time'];

async function api(path, options = {}) {
  const r = await fetch(`${API}${path}`, options);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || 'Request failed');
  return data;
}

function Metric({ label, value, sub }) { return <div className="metric"><div className="muted">{label}</div><strong>{value}</strong>{sub && <small>{sub}</small>}</div> }

function ChartView({ result }) {
  if (!result?.rows?.length || result.chart === 'kpi') return null;
  const data = result.rows;
  const xKey = result.columns?.[0]; const yKey = result.columns?.[1];
  if (!xKey || !yKey) return null;
  const numeric = typeof data[0]?.[yKey] === 'number';
  if (!numeric) return null;
  if (result.chart === 'pie') return <ResponsiveContainer width="100%" height={320}><PieChart><Pie data={data} dataKey={yKey} nameKey={xKey} outerRadius={110}>{data.map((_,i)=><Cell key={i} fill={`hsl(${i*45} 70% 55%)`}/>)}</Pie><Tooltip/></PieChart></ResponsiveContainer>;
  const line = result.chart === 'line';
  return <ResponsiveContainer width="100%" height={320}>{line ? <AreaChart data={data}><CartesianGrid strokeDasharray="3 3"/><XAxis dataKey={xKey}/><YAxis/><Tooltip/><Area type="monotone" dataKey={yKey} fill="rgba(124,92,255,.28)" stroke="#8b5cf6"/></AreaChart> : <BarChart data={data}><CartesianGrid strokeDasharray="3 3"/><XAxis dataKey={xKey}/><YAxis/><Tooltip/><Bar dataKey={yKey} fill="#22c55e" radius={[8,8,0,0]}/></BarChart>}</ResponsiveContainer>;
}

function DataTable({ result }) {
  if (!result?.rows?.length) return <div className="empty">No rows returned.</div>;
  return <div className="table-wrap"><table><thead><tr>{result.columns.map(c=><th key={c}>{c}</th>)}</tr></thead><tbody>{result.rows.slice(0,50).map((row,i)=><tr key={i}>{result.columns.map(c=><td key={c}>{String(row[c] ?? '')}</td>)}</tr>)}</tbody></table></div>
}

function App() {
  const [datasets, setDatasets] = useState([]); const [active, setActive] = useState(null); const [preview, setPreview] = useState(null);
  const [question, setQuestion] = useState(''); const [result, setResult] = useState(null); const [history, setHistory] = useState([]); const [loading, setLoading] = useState(false); const [error, setError] = useState('');
  const [showSQL, setShowSQL] = useState(true); const [tab, setTab] = useState('insights');

  async function refresh() { const ds = await api('/datasets'); setDatasets(ds); if (!active && ds[0]) setActive(ds[0]); }
  useEffect(()=>{ refresh().catch(e=>setError(e.message)); },[]);
  useEffect(()=>{ if(active){ api(`/datasets/${active.id}/preview`).then(setPreview).catch(e=>setError(e.message)); api(`/history?dataset_id=${active.id}`).then(setHistory).catch(()=>{}); setResult(null); } },[active]);

  async function upload(file) { setError(''); const fd = new FormData(); fd.append('file', file); try { const d = await api('/upload',{method:'POST',body:fd}); await refresh(); setActive(d); } catch(e){setError(e.message)} }
  async function demo(){ try{const d=await api('/demo',{method:'POST'}); await refresh(); setActive(d)}catch(e){setError(e.message)} }
  async function analyze(){ if(!active || !question.trim()) return; setLoading(true); setError(''); try { const r=await api('/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({dataset_id:active.id,question})}); setResult(r); setHistory(await api(`/history?dataset_id=${active.id}`)); setTab('insights'); } catch(e){setError(e.message)} finally{setLoading(false)} }
  async function remove(id){ if(!confirm('Delete this dataset?')) return; await api(`/datasets/${id}`,{method:'DELETE'}); setActive(null); setPreview(null); setResult(null); await refresh(); }

  const stats = useMemo(()=> active ? {rows:active.rows, cols:active.columns_count} : null,[active]);

  return <div className="app">
    <header className="topbar"><div className="brand"><div className="logo"><Sparkles size={18}/></div><span>InsightFlow</span><small>AI DATA ANALYST</small></div><div className="top-actions"><span className="status"><span className="dot"/> API Online</span><button className="ghost" onClick={demo}>Load demo</button></div></header>
    <section className="hero"><div className="hero-copy"><div className="eyebrow"><Bot size={16}/> Autonomous analytics workspace</div><h1>Ask your data anything.<br/><span>Get the answer instantly.</span></h1><p>Upload a CSV, connect a trusted SQL database, and let an AI analyst plan SQL, run analysis, surface insights and build charts.</p><div className="hero-pills"><span><ShieldCheck size={14}/> Read-only SQL guardrails</span><span><Code2 size={14}/> Explainable SQL</span><span><BarChart3 size={14}/> Interactive charts</span></div></div><div className="flow"><div className="flow-title">Agent workflow</div><div className="flow-step active"><span>01</span><b>Understand</b><small>Interpret the question</small></div><ChevronRight/><div className="flow-step"><span>02</span><b>Query</b><small>Generate safe SQL</small></div><ChevronRight/><div className="flow-step"><span>03</span><b>Analyze</b><small>Compute & validate</small></div><ChevronRight/><div className="flow-step"><span>04</span><b>Visualize</b><small>Answer + chart</small></div></div></section>

    <main className="workspace">
      <aside className="sidebar">
        <div className="side-head"><div><b>Data sources</b><small>{datasets.length} connected</small></div><Database size={18}/></div>
        <label className="upload"><Upload size={18}/><span>Upload CSV</span><input type="file" accept=".csv" onChange={e=>e.target.files[0] && upload(e.target.files[0])}/></label>
        <div className="dataset-list">{datasets.map(d=><div key={d.id} className={`dataset ${active?.id===d.id?'selected':''}`} onClick={()=>setActive(d)}><div className="dataset-icon"><Table2 size={16}/></div><div className="dataset-info"><b>{d.name}</b><small>{d.rows.toLocaleString()} rows · {d.columns_count} cols</small></div><button title="Delete" onClick={(e)=>{e.stopPropagation();remove(d.id)}}><Trash2 size={15}/></button></div>)}</div>
        <div className="side-tip"><Sparkles size={16}/><div><b>AI mode</b><small>{datasets.length ? 'Heuristic fallback works locally. Add OPENAI_API_KEY for LLM planning.' : 'Load the demo dataset to try it now.'}</small></div></div>
      </aside>

      <section className="content">
        {!active ? <div className="welcome"><div className="welcome-icon"><Bot size={34}/></div><h2>Welcome to InsightFlow</h2><p>Start with the sample sales dataset or upload your own CSV.</p><button className="primary" onClick={demo}><Sparkles size={17}/> Try demo dataset</button></div> : <>
          <div className="dataset-banner"><div><span className="eyebrow">Active dataset</span><h2>{active.name}</h2><small>{active.rows.toLocaleString()} rows · {active.columns_count} columns</small></div><div className="metrics"><Metric label="Rows" value={stats.rows.toLocaleString()}/><Metric label="Columns" value={stats.cols}/><Metric label="Null values" value={active.columns.reduce((a,c)=>a+c.nulls,0).toLocaleString()}/></div></div>
          <div className="question-box"><div className="q-label"><span>Ask the analyst</span><small>Natural language → SQL → insight</small></div><textarea value={question} onChange={e=>setQuestion(e.target.value)} placeholder="e.g. Show total revenue by product and identify the top performer" onKeyDown={e=>{if(e.key==='Enter'&&e.ctrlKey)analyze()}}/><div className="q-bottom"><div className="suggestions">{EXAMPLES.map(x=><button key={x} onClick={()=>setQuestion(x)}>{x}</button>)}</div><button className="primary" disabled={loading} onClick={analyze}>{loading?<span className="spinner"/>:<Send size={16}/>} {loading?'Analyzing':'Analyze data'}</button></div></div>
          {error && <div className="error">{error}</div>}
          <div className="tabs"><button className={tab==='insights'?'on':''} onClick={()=>setTab('insights')}>Insights</button><button className={tab==='preview'?'on':''} onClick={()=>setTab('preview')}>Data preview</button><button className={tab==='history'?'on':''} onClick={()=>setTab('history')}>History</button><button className={tab==='sql'?'on':''} onClick={()=>setTab('sql')}>SQL console</button></div>
          {tab==='insights' && <div className="results">
            {result ? <><div className="answer-card"><div className="answer-head"><div className="ai-badge"><Bot size={16}/></div><div><span className="eyebrow">Analyst conclusion</span><h3>{result.answer}</h3></div><span className="engine">{result.engine}</span></div><ChartView result={result}/><DataTable result={result}/></div><div className="sql-card"><button onClick={()=>setShowSQL(!showSQL)}><Code2 size={16}/> Generated SQL <span>{showSQL?'Hide':'Show'}</span></button>{showSQL&&<pre>{result.sql}</pre>}</div></> : <div className="empty-state"><Bot size={30}/><b>Your answer will appear here</b><span>Choose a question or type your own query.</span></div>}
          </div>}
          {tab==='preview' && <div className="panel"><div className="panel-head"><div><h3>Dataset preview</h3><small>First 25 rows</small></div></div><DataTable result={{columns:preview?.dataset.columns.map(c=>c.name) || [], rows:preview?.rows || []}}/></div>}
          {tab==='history' && <div className="panel"><div className="panel-head"><div><h3>Conversation history</h3><small>Saved locally on this server</small></div></div>{history.length ? history.map(h=><button className="history-row" key={h.id} onClick={()=>{setQuestion(h.question);setTab('insights')}}><span>{h.question}</span><small>{h.answer}</small></button>) : <div className="empty">No questions yet.</div>}</div>}
          {tab==='sql' && <SQLConsole active={active} onResult={setResult} setError={setError}/>} 
        </>}
      </section>
    </main>
    <footer>InsightFlow · AI Data Analyst Agent · Built with React, FastAPI, DuckDB and optional OpenAI</footer>
  </div>
}

function SQLConsole({active,onResult,setError}){
  const [sql,setSQL] = useState(`SELECT * FROM "dataset_${active.id}" LIMIT 20`); const [out,setOut]=useState(null);
  async function run(){setError('');try{const r=await api('/sql',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({dataset_id:active.id,sql})});setOut(r)}catch(e){setError(e.message)}}
  return <div className="panel"><div className="panel-head"><div><h3>SQL console</h3><small>Read-only SELECT/WITH queries only</small></div><button className="primary" onClick={run}><Play size={15}/> Run</button></div><textarea className="sql-editor" value={sql} onChange={e=>setSQL(e.target.value)}/>{out&&<DataTable result={out}/>}</div>
}

createRoot(document.getElementById('root')).render(<App/>);
