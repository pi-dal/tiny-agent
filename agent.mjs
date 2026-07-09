#!/usr/bin/env node
// mini-agent — Node.js port — TUI agent with bash tool + sessions. Needs: npm install openai

import fs from "fs";import path from "path";import os from "os";import {execSync} from "child_process";
import {createInterface} from "readline";import {randomUUID} from "crypto";import OpenAI from "openai";
import {fileURLToPath} from "url";
const __dirname=path.dirname(fileURLToPath(import.meta.url));

function loadDotenv(){const p=path.join(__dirname,".env");if(!fs.existsSync(p))return;
for(const l of fs.readFileSync(p,"utf-8").split("\n")){const t=l.trim();if(!t||t.startsWith("#")||!t.includes("="))continue;
const i=t.indexOf("=");const k=t.slice(0,i).trim(),v=t.slice(i+1).trim().replace(/^["']|["']$/g,"");
if(!process.env[k])process.env[k]=v;}}
loadDotenv();

const MODEL=process.env.AGENT_MODEL||"gpt-4o-mini",BASE_URL=process.env.AGENT_BASE_URL||null,
DIR=path.resolve(process.env.AGENT_SESSIONS_DIR||path.join(os.homedir(),".agent","sessions")),
SYS="You are a helpful AI assistant with access to a bash tool. You can run shell commands to help the user accomplish tasks. Always explain briefly what you are doing, then call the tool. Be concise.",
TOOL={type:"function",function:{name:"bash",description:"Execute a shell command and return its output.",
parameters:{type:"object",properties:{command:{type:"string",description:"The shell command to execute."}},required:["command"]}}};

function sh(cmd){try{const r=execSync(cmd,{shell:true,timeout:120e3,maxBuffer:8e3});return r.toString().slice(0,8e3)||`[exit code 0]`}
catch(e){if(e.stderr)return e.stderr.toString().slice(0,8e3);if(e.stdout)return e.stdout.toString().slice(0,8e3);return`[Error: ${e.message}]`}}
function tool(name,args){return name==="bash"?sh(args.command||""):`[Unknown: ${name}]`}

class Session{constructor(sid=null){fs.mkdirSync(DIR,{recursive:true});this.id=sid||randomUUID().slice(0,12);
this.p=path.join(DIR,`${this.id}.jsonl`);this.msgs=[];this.created=new Date().toISOString();
if(fs.existsSync(this.p))this.load();else fs.writeFileSync(this.p,JSON.stringify({type:"meta",id:this.id,created:this.created})+"\n");}
load(){for(const l of fs.readFileSync(this.p,"utf-8").split("\n").filter(Boolean))try{const d=JSON.parse(l);
if(d.type==="meta")this.created=d.created||this.created;else this.msgs.push(d)}catch{}}
append(m){this.msgs.push(m);fs.appendFileSync(this.p,JSON.stringify(m)+"\n")}
static list(){const r=[];if(!fs.existsSync(DIR))return r;
const f=fs.readdirSync(DIR).filter(x=>x.endsWith(".jsonl")).map(x=>({n:x,m:fs.statSync(path.join(DIR,x)).mtimeMs})).sort((a,b)=>b.m-a.m);
for(const {n} of f){try{const ls=fs.readFileSync(path.join(DIR,n),"utf-8").split("\n").filter(Boolean);if(!ls.length)continue;
const meta=JSON.parse(ls[0]),msgs=ls.slice(1).map(l=>JSON.parse(l));
r.push({id:meta.id||n.replace(".jsonl",""),created:meta.created||"?",msgs:msgs.length,preview:msgs[0]?.content?.slice(0,50)||""})}catch{}}return r}}

class Agent{constructor(model=MODEL,baseUrl=BASE_URL,apiKey=null){const o={apiKey:apiKey||process.env.OPENAI_API_KEY};
if(baseUrl)o.baseURL=baseUrl;this.c=new OpenAI(o);this.m=model;}
async call(m){return await this.c.chat.completions.create({model:this.m,messages:m,tools:[TOOL],tool_choice:"auto"})}}

const B=`\n  ╔══════════════════════════════════════╗\n  ║     mini-agent — bash-powered AI      ║\n  ╠══════════════════════════════════════╣\n  ║  /new /sessions /load /clear /exit    ║\n  ╚══════════════════════════════════════╝`;

function d(t){return`\x1b[2m${t}\x1b[22m`}function b(t){return`\x1b[1m${t}\x1b[22m`}
function c(t){return`\x1b[36m${t}\x1b[39m`}function g(t){return`\x1b[32m${t}\x1b[39m`}
function y(t){return`\x1b[33m${t}\x1b[39m`}function r(t){return`\x1b[31m${t}\x1b[39m`}

function render(s){for(const m of s.msgs){if(m.role==="user"){console.log(`${c("You:")} ${m.content||""}`)}
else if(m.role==="assistant"){if(m.content){console.log(`${g("Agent:")}`);console.log(m.content)}
for(const tc of m.tool_calls||[]){let a={};try{a=JSON.parse(tc.function.arguments)}catch{}
console.log(`  ${y("🔧")} ${a.command||""}`);const tid=tc.id
for(const m2 of s.msgs){if(m2.role==="tool"&&m2.tool_call_id===tid){console.log(`  ${d("╔═ output")}\n  ${(m2.content||"").slice(0,500)}\n  ${d("╚"+"═".repeat(50))}`);break}}}}}}

async function loop(agent,session){const msgs=[...session.msgs];if(!msgs.length||msgs[0].role!=="system")msgs.unshift({role:"system",content:SYS});
while(true){let resp;try{resp=await agent.call(msgs)}catch(e){console.log(`${r("Error:")} ${e.message}`);return}
const msg=resp.choices[0].message,entry={role:"assistant",content:msg.content||null};
if(msg.tool_calls){entry.tool_calls=msg.tool_calls.map(tc=>({id:tc.id,type:"function",function:{name:tc.function.name,arguments:tc.function.arguments}}))}
session.append(entry);if(msg.content){console.log(`${g("Agent:")}`);console.log(msg.content)}
if(!msg.tool_calls||!msg.tool_calls.length)return;
for(const tc of msg.tool_calls){let a={};try{a=JSON.parse(tc.function.arguments)}catch{}
console.log(`  ${y("🔧")} ${a.command||""}`);const result=tool(tc.function.name,a);
session.append({role:"tool",tool_call_id:tc.id,content:result});
console.log(`  ${d("╔═ output")}\n  ${result.slice(0,2e3)}\n  ${d("╚"+"═".repeat(50))}`)}
msgs.length=0;msgs.push(...session.msgs);if(msgs[0].role!=="system")msgs.unshift({role:"system",content:SYS})}}

function cmd(text,agent,session){const c2=text.toLowerCase();
if(c2==="/exit"||c2==="/quit")return[session,true];
if(c2==="/help"){console.log(d("Commands: /new /sessions /load <id> /clear /help /exit"))}
else if(c2==="/new"){session=new Session();console.log(d(`New session: ${session.id}`))}
else if(c2==="/sessions"){const ss=Session.list();if(!ss.length)console.log(d("No saved sessions."));
else for(const s of ss)console.log(`  ${b(s.id)} (${s.msgs} msgs) ${s.preview}`)}
else if(c2.startsWith("/load ")){const sid=c2.slice(6).trim();session=new Session(sid);console.log(d(`Loaded ${session.id} (${session.msgs.length} msgs)`));render(session)}
else if(c2==="/clear")console.clear();
return[session,false]}

async function main(){const args=process.argv.slice(2);let sid=null,model=MODEL,baseUrl=BASE_URL;
for(let i=0;i<args.length;i++){if(args[i]==="--session"||args[i]==="-s")sid=args[++i];else if(args[i]==="--model"||args[i]==="-m")model=args[++i];else if(args[i]==="--base-url")baseUrl=args[++i]}
if(!process.env.OPENAI_API_KEY){console.error(`${r("Error:")} OPENAI_API_KEY not set.`);process.exit(1)}
const agent=new Agent(model,baseUrl),session=sid?new Session(sid):new Session();
console.log(B);if(session.msgs.length)render(session);
const rl=createInterface({input:process.stdin,output:process.stdout});
const ask=()=>{rl.question(`${c("You:")} `,async input=>{const t=input.trim();if(!t){ask();return}
if(t.startsWith("/")){const[ns,exit]=cmd(t,agent,session);session=ns;if(exit){rl.close();return}ask();return}
session.append({role:"user",content:t});await loop(agent,session);ask()})};ask()}
main().catch(e=>console.error(`${r("Fatal:")} ${e.message}`));
