"use client";
import { useEffect, useRef, useState } from "react";
import { api, download } from "@/lib/api";
import { useStore } from "@/lib/store";
import { canApprove, type Workflow } from "@/lib/workflow";
import type { CV } from "@/lib/types";
import { Alert, Button, Textarea, Input } from "./ui";

type Session = {key: string; job: string; workflow?: string; exports?: string[]; approvalKey: string};
const STORAGE = "passefiltre:workflow-review";
function restore(): Session | null {
  try { return JSON.parse(sessionStorage.getItem(STORAGE) || "null"); } catch { return null; }
}

const LABELS: Record<string,string> = {summary:"Résumé",headline:"Titre",experience:"Expériences",skills:"Compétences",
  cleanup:"Corrections",ats_review:"Audit ATS",score:"Score",strengths:"Points forts",improvements:"Améliorations",
  missing_keywords:"Mots-clés absents",description:"Description",reason:"Explication",suggestions:"Propositions",
  title:"Intitulé",company:"Entreprise",education:"Formation",school:"Établissement",degree:"Diplôme",field:"Domaine"};
function Proposal({value}: {value: unknown}) {
  if (value == null) return null;
  if (Array.isArray(value)) return <ul className="ml-4 list-disc space-y-2">{value.map((v,i)=><li key={i}><Proposal value={v}/></li>)}</ul>;
  if (typeof value === "object") return <div className="space-y-2">{Object.entries(value).filter(([k])=>k!=="id").map(([k,v])=>
    <div key={k}><span className="font-medium">{LABELS[k] ?? k} : </span><Proposal value={v}/></div>)}</div>;
  return <span className="whitespace-pre-wrap text-sm">{String(value)}</span>;
}

export function WorkflowPanel() {
  const { cv, server } = useStore();
  const [session, setSession] = useState<Session | null>(null);
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [draft, setDraft] = useState<CV | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [useAI, setUseAI] = useState(true);
  const [downloads, setDownloads] = useState<string[]>([]);
  const mounted = useRef(true);
  useEffect(() => { setSession(restore()); mounted.current = true; return () => {mounted.current=false;}; }, []);
  const remember = (s: Session | null) => {
    setSession(s);
    try { if (s) sessionStorage.setItem(STORAGE, JSON.stringify(s)); else sessionStorage.removeItem(STORAGE); } catch { /* memory remains */ }
  };
  useEffect(() => {
    if (!session) return;
    let stopped=false;
    let timer: ReturnType<typeof setTimeout>;
    const poll=async () => {
      try {
        if (!session.workflow) {
          const job=await api.workflowJob(session.job,session.key);
          if (stopped) return;
          if (job.status==="succeeded" && job.result) remember({...session,workflow:job.result.resource_id});
          else if (["failed","cancelled","expired"].includes(job.status)) setError(job.error?.message || "Traitement interrompu.");
          else timer=setTimeout(poll,1200);
        } else if (!workflow || workflow.id!==session.workflow) {
          const value=await api.workflow(session.workflow,session.key);
          if (!stopped) {setWorkflow(value);setDraft(value.data.draft);setConfirmed(false);}
        }
        if (session.exports) {
          const jobs=await Promise.all(session.exports.map(id=>api.workflowJob(id,session.key)));
          if (stopped) return;
          setDownloads(jobs.filter(j=>j.status==="succeeded" && j.result).map(j=>j.result!.resource_id));
          const failed=jobs.find(j=>["failed","cancelled","expired"].includes(j.status));
          if (failed) setError(failed.error?.message || "Export interrompu.");
          else if (jobs.some(j=>j.status!=="succeeded")) timer=setTimeout(poll,1200);
        }
      } catch (e) {if (!stopped) setError((e as Error).message);}
    };
    poll();
    return ()=>{stopped=true;clearTimeout(timer);};
    // The session contains all identifiers needed to resume after reload.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  },[session]);

  async function action(fn:()=>Promise<void>) {
    setBusy(true);setError("");
    try {await fn();} catch(e) {if(mounted.current)setError((e as Error).message);}
    finally {if(mounted.current)setBusy(false);}
  }
  if (!server?.persistent_workflows) return null;
  const edit=(value:CV)=>{setDraft(value);setConfirmed(false);setDownloads([]);};
  const editable=workflow?.data.status==="awaiting_review";
  return <section className="space-y-4 rounded-lg border border-line bg-white p-5">
    <h2 className="text-lg font-semibold">CV ciblé avec validation</h2>
    <p className="text-sm text-muted">Vérifiez les faits et les formulations avant de valider cette version pour l’export.</p>
    {error && <Alert>{error}</Alert>}
    {!session ? <>
      <label className="flex gap-2 text-sm"><input type="checkbox" checked={useAI} disabled={!server.llm.server_key}
        onChange={e=>setUseAI(e.target.checked)}/> Demander aussi des propositions IA au fournisseur du serveur</label>
      <Button disabled={busy || !cv.settings.target.offer_text.trim()} onClick={()=>action(async()=>{
        const job=await api.workflowStart(cv,useAI && server.llm.server_key);
        remember({key:job.key,job:job.id,approvalKey:crypto.randomUUID()});
      })}>Préparer le CV ciblé</Button>
      {!cv.settings.target.offer_text.trim() && <p className="text-sm text-muted">Renseignez d’abord le texte de l’offre.</p>}
    </> : !workflow ? <>
      <p role="status">Préparation du brouillon…</p>
      <Button disabled={busy} variant="secondary" onClick={()=>action(async()=>{
        await api.workflowCancel(session.job,session.key);remember(null);
      })}>Annuler</Button>
    </> : draft && <>
      <p className="text-sm">Poste : {draft.settings.target.title} · Score ATS : {workflow.data.before_ats.score} → {workflow.data.after_ats.score}</p>
      {workflow.data.suggestions && <details className="rounded border border-line p-3">
        <summary>Propositions IA à vérifier</summary>
        <p className="my-2 text-sm">{workflow.data.suggestions.notice}</p>
        <Proposal value={workflow.data.suggestions.suggestions}/>
      </details>}
      <details className="rounded border border-line p-3"><summary>Consulter les faits du CV source</summary>
        <p className="mt-2 whitespace-pre-wrap text-sm">{workflow.data.source.profile.basics.summary}</p>
        {workflow.data.source.profile.experience.map(e=><article key={e.id} className="mt-3 text-sm">
          <strong>{e.title} — {e.company}</strong><p className="whitespace-pre-wrap">{e.description}</p></article>)}
        <p className="mt-3 text-sm">Compétences : {workflow.data.source.profile.skills.map(s=>s.name).join(", ")}</p>
      </details>
      <label className="block text-sm">Titre du CV<Input disabled={!editable} value={draft.profile.basics.headline}
        onChange={e=>edit({...draft,profile:{...draft.profile,basics:{...draft.profile.basics,headline:e.target.value}}})}/></label>
      <label className="block text-sm">Résumé<Textarea rows={5} disabled={!editable} value={draft.profile.basics.summary}
        onChange={e=>edit({...draft,profile:{...draft.profile,basics:{...draft.profile.basics,summary:e.target.value}}})}/></label>
      {draft.profile.experience.map((experience,i)=><label key={experience.id} className="block text-sm">
        {experience.title} — {experience.company}<Textarea rows={4} disabled={!editable} value={String(experience.description ?? "")}
          onChange={e=>edit({...draft,profile:{...draft.profile,experience:draft.profile.experience.map((x,j)=>j===i?{...x,description:e.target.value}:x)}})}/>
      </label>)}
      {editable ? <>
        <Button variant="secondary" disabled={busy} onClick={()=>action(async()=>{
          const saved=await api.workflowSave(workflow.id,session.key,workflow.version,draft);
          setWorkflow(saved);setDraft(saved.data.draft);setConfirmed(false);
          remember({...session,approvalKey:crypto.randomUUID()});
        })}>Enregistrer mes corrections</Button>
        <label className="flex gap-2 text-sm"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>
          J’ai relu cette version et je confirme que mes qualifications et expériences sont exactes.</label>
        {JSON.stringify(draft)!==JSON.stringify(workflow.data.draft) && <p className="text-sm text-muted">Enregistrez vos corrections avant de valider.</p>}
        <div className="flex gap-2"><Button disabled={busy || !canApprove(workflow,draft,confirmed)} onClick={()=>action(async()=>{
          const result=await api.workflowApprove(workflow.id,session.key,workflow.version,workflow.data.digest,session.approvalKey);
          setWorkflow({...workflow,data:{...workflow.data,status:"approved"}});
          remember({...session,exports:result.jobs.map(j=>j.id)});
        })}>Valider et préparer PDF / Word</Button>
        <Button variant="secondary" disabled={busy} onClick={()=>action(async()=>{
          await api.workflowReject(workflow.id,session.key);remember(null);setWorkflow(null);setDraft(null);
        })}>Rejeter</Button></div>
      </> : <p className="text-sm">{workflow.data.status==="approved" ? "Version validée." : "Workflow terminé."}</p>}
      {downloads.map((id,i)=><Button key={id} variant="secondary" disabled={busy} onClick={()=>action(async()=>{
        const file=await api.workflowDownload(id,session.key);download(file.blob,file.filename);
      })}>Télécharger le document {i+1}</Button>)}
      {!editable && <Button variant="ghost" onClick={()=>{remember(null);setWorkflow(null);setDraft(null);setDownloads([]);}}>Nouveau CV ciblé</Button>}
    </>}
  </section>;
}
