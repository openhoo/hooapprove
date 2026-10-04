// Cross-service acceptance using the actual Shooping adapter and HooApprove HTTP API.
// All REWE/account/order values are synthetic. No upstream REWE network is used.
import assert from 'node:assert/strict';
import {generateKeyPairSync,randomBytes,createHash,sign} from 'node:crypto';
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
  const {privateKey,publicKey}=generateKeyPairSync('ed25519');
  const device_id=randomBytes(16).toString('hex');
  const public_key=publicKey.export({type:'spki',format:'der'}).subarray(-32).toString('hex');
  const pairing=await (await fetch(base+'/v1/pairings',{method:'POST',headers:{authorization:'Bearer '+token,'content-type':'application/json'},body:JSON.stringify({subject:'demo-human',label:'Synthetic REWE owner'})})).json();
  const ticketDigest=createHash('sha256').update(pairing.ticket).digest('hex');
  const signature=sign(null,Buffer.from(`hooapprove.pair.v1\n${ticketDigest}\n${device_id}\n${public_key}`),privateKey).toString('hex');
  const enrolled=await fetch(base+'/api/pairings/enroll',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({ticket:pairing.ticket,device_id,public_key,signature})});
  assert.equal(enrolled.status,201);
  async function deviceRequest(path,body){
    const method=body===undefined?'GET':'POST',raw=body===undefined?'':JSON.stringify(body);
    const timestamp=String(Math.floor(Date.now()/1000)),nonce=randomBytes(16).toString('hex');
    const digest=createHash('sha256').update(raw).digest('hex');
    const message=`hooapprove.device.v1\n${device_id}\n${method}\n${path}\n${timestamp}\n${nonce}\n${digest}`;
    return fetch(base+path,{method,headers:{'content-type':'application/json','x-device-id':device_id,'x-device-time':timestamp,'x-device-nonce':nonce,'x-device-signature':sign(null,Buffer.from(message),privateKey).toString('hex')},body:body===undefined?undefined:raw});
  }
  const requests=await (await deviceRequest('/api/requests')).json();
  const request=requests.find(item=>item.id===preview.approvalRequestId);assert.equal(request.status,'pending');
  assert.ok(request.details.some(item=>item.value.includes('2 × Brot')));
  const decision=await deviceRequest(`/api/requests/${request.id}/decision`,{decision:'approve',digest:request.digest});
  assert.equal(decision.status,200);
  const order=await shopping.submitOrder(preview.digest);assert.equal(order.orderState,'accepted');assert.equal(orders,1);
  const result=await (await fetch(base+`/v1/requests/${request.id}`,{headers:{authorization:'Bearer '+token}})).json();
  assert.equal(result.status,'completed');assert.equal(result.reference,'synthetic-order-1');
  await assert.rejects(shopping.submitOrder(preview.digest));assert.equal(orders,1);
  console.log(JSON.stringify({approvalApi:'actual HTTP',adapter:'actual Shooping',upstream:'synthetic REWE',pendingBlocked:true,humanApproval:true,savedOrders:orders,completed:true,replayBlocked:true}));
} finally {await rm(directory,{recursive:true,force:true});}
