import assert from 'node:assert/strict';
import { canApprove } from '../lib/workflow.ts';
const draft = {profile: {basics: {headline: 'Engineer'}}};
const workflow = {id:'one',version:1,data:{status:'awaiting_review',draft}};
assert.equal(canApprove(workflow as never,draft as never,false),false);
assert.equal(canApprove(workflow as never,draft as never,true),true);
assert.equal(canApprove({...workflow,data:{...workflow.data,status:'approved'}} as never,draft as never,true),false);
assert.equal(canApprove(workflow as never,{...draft,profile:{basics:{headline:'Changed'}}} as never,true),false);
