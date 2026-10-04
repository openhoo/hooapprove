// Cross-service acceptance using the actual Shooping adapter and HooApprove HTTP API.
// All REWE/account/order values are synthetic. No upstream REWE network is used.
import assert from 'node:assert/strict';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';

const [base,worktree]=process.argv.slice(2);
const load=name=>import(pathToFileURL(join(worktree,'dist',name)).href);
const {Shopping}=await load('shopping.js');
const {HooApprove}=await load('hooapprove.js');
const {SessionStore,privateJson}=await load('store.js');
const token='wire-proof-service-'+'a'.repeat(40);
const directory=await mkdtemp(join(tmpdir(),'hooapprove-wire-'));
try {
  const store=new SessionStore(join(directory,'session.json'));
  await privateJson(store.path,{zipCode:'10115',marketId:'synthetic',serviceType:'DELIVERY',basketId:'basket',checkoutId:'checkout',appImportSourceHash:'synthetic-account-binding',tokens:{access_token:'synthetic-not-a-real-token',expires_at:Date.now()+300000}});
  let orders=0;
  const upstream={request:async(_,path)=>{
    if(path==='/api/baskets')return {data:{basket:{id:'basket',version:1,lineItems:[{title:'Brot',quantity:2,totalPrice:1200}],summary:{totalPrice:1200}}}};
    if(path.endsWith('/confirmations'))return {data:{checkout:{id:'checkout',basketId:'basket',selectedDeliveryAddress:{id:'synthetic-address',street:'Beispielstraße',houseNumber:'12'},timeslot:{id:'synthetic-slot'},payment:{paymentMethod:'DIRECT_DEBIT'}},basket:{id:'basket',version:1,summary:{totalPrice:1200}}}};
    if(path.endsWith('/orders')){orders++;return {data:{order:{orderId:'synthetic-order-1'}}};}
    throw Error('Unexpected synthetic request');
  }};
  const gate=new HooApprove({url:base,token,service:'rewe',subject:'demo-human',waitSeconds:0},store.path);
  const shopping=new Shopping(store,upstream,gate);
  const preview=await shopping.prepareOrder();
  assert.ok(preview.approvalRequestId);
  await assert.rejects(shopping.submitOrder(preview.digest));assert.equal(orders,0);
  const signedIn=await fetch(base+'/auth/login',{redirect:'manual'});
  const cookie=signedIn.headers.getSetCookie()[0].split(';')[0];
  const me=await (await fetch(base+'/api/me',{headers:{cookie}})).json();
  const requests=await (await fetch(base+'/api/requests',{headers:{cookie}})).json();
  const request=requests.find(item=>item.id===preview.approvalRequestId);assert.equal(request.status,'pending');
  assert.ok(request.details.some(item=>item.value.includes('2 × Brot')));
  const decision=await fetch(base+`/api/requests/${request.id}/decision`,{method:'POST',headers:{cookie,origin:base,'x-csrf-token':me.csrf,'content-type':'application/json'},body:JSON.stringify({decision:'approve',digest:request.digest})});
  assert.equal(decision.status,200);
  const order=await shopping.submitOrder(preview.digest);assert.equal(order.orderState,'accepted');assert.equal(orders,1);
  const result=await (await fetch(base+`/v1/requests/${request.id}`,{headers:{authorization:'Bearer '+token}})).json();
  assert.equal(result.status,'completed');assert.equal(result.reference,'synthetic-order-1');
  await assert.rejects(shopping.submitOrder(preview.digest));assert.equal(orders,1);
  console.log(JSON.stringify({approvalApi:'actual HTTP',adapter:'actual Shooping',upstream:'synthetic REWE',pendingBlocked:true,humanApproval:true,savedOrders:orders,completed:true,replayBlocked:true}));
} finally {await rm(directory,{recursive:true,force:true});}
