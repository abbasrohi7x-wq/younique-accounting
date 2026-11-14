/* Direct regression probe for the extracted finance engine modules. */
const path=require('path');
/* Exercise the extracted finance engine directly, independent of the browser DOM. */
const assert=require('assert');
const {createEngine}=require('../src/engine/core.js');
const {createFin}=require('../src/engine/fin.js');
let idSeq=0,docSeq=0;
const financeDB={
  journal:[],sales:[],purchases:[],saleItems:[],purchaseItems:[],payments:[],
  stockMoves:[],returns:[],cashSessions:[],cashMovements:[],
  warehouses:[{id:'MAIN',name:'انبار اصلی',active:true},{id:'W2',name:'انبار دوم',active:true}],
  warehouseStocks:{MAIN:{},W2:{}},variants:[{id:'v1',stock:0,buyPrice:0}],
  costing:{method:'weighted_average'},costLayers:{},
  taxProfile:{enabled:true,vatRate:10,vatMode:'exclusive'}
};
const n=x=>Number(x)||0;
const round=x=>Math.round((n(x)+Number.EPSILON)*100)/100;
const helpers={
  uid:()=> 'id-'+(++idSeq), now:()=> '2026-11-14T00:00:00.000Z', num:n, roundMoney:round,
  cloneDB:()=>JSON.parse(JSON.stringify(financeDB)), normalize:x=>x,
  saveDB:()=>true, audit:()=>{}, invalidate:()=>{},
  variantBy:id=>financeDB.variants.find(v=>v.id===id),
  variantName:v=>v&&v.id||'?', nextNumber:type=>'T-'+type+'-'+(++docSeq),
  paymentAccount:m=>m==='card'?'card':m==='bank'?'bank':'cash',
  saleByNo:ref=>financeDB.sales.find(x=>x.number===ref||x.id===ref),
  purchaseByNo:ref=>financeDB.purchases.find(x=>x.number===ref||x.id===ref)
};
const engine=createEngine(financeDB,helpers);
const fin=createFin(financeDB,helpers,engine);
engine.openCashSession(1000000,'headless test','test');
const purchase=engine.createPurchase({
  supplierId:'supplier-1',
  items:[{variantId:'v1',qty:4,unitPrice:1000}],
  payments:{cash:4400,card:0,bank:0,credit:0},warehouseId:'W2'
});
assert.strictEqual(purchase.purchase.total,4400);
assert.strictEqual(purchase.purchase.netTotal,4000);
assert.strictEqual(purchase.purchase.vat,400);
assert.strictEqual(financeDB.warehouseStocks.W2.v1,4);
assert.strictEqual(financeDB.warehouseStocks.MAIN.v1||0,0);
const sale=engine.createSale({
  items:[{variantId:'v1',qty:2,unitPrice:1500}],
  customerId:'customer-1',payments:{cash:3300,card:0,bank:0,credit:0},warehouseId:'W2'
});
assert.strictEqual(sale.sale.total,3300);
assert.strictEqual(financeDB.warehouseStocks.W2.v1,2);
const saleReturn=fin.saleReturn({ref:sale.number,qtys:{[sale.items[0].id]:1},method:'credit'});
assert.strictEqual(saleReturn.vat,150);
assert.strictEqual(saleReturn.warehouseId,'W2');
const purchaseReturn=fin.purchaseReturn({ref:purchase.number,qtys:{[purchase.items[0].id]:1},method:'credit'});
assert.strictEqual(purchaseReturn.vat,100);
assert.strictEqual(purchaseReturn.total,1100);
assert.strictEqual(purchaseReturn.warehouseId,'W2');
assert.strictEqual(financeDB.warehouseStocks.W2.v1,2);
assert.strictEqual(financeDB.variants[0].stock,2);
assert.strictEqual(financeDB.stockMoves.every(x=>x.warehouseId==='W2'),true);
const migrated={id:'v2',stock:4,buyPrice:500};
financeDB.variants.push(migrated);financeDB.warehouseStocks.MAIN.v2=4;
delete financeDB.costLayers.v2;
engine.createPurchase({
  items:[{variantId:'v2',qty:2,unitPrice:1000}],
  payments:{cash:2200,card:0,bank:0,credit:0},warehouseId:'MAIN'
});
const layer=financeDB.costLayers.v2[0];
assert.strictEqual(migrated.stock,6);
assert.strictEqual(layer.value,4000);
assert.ok(Math.abs(layer.unitCost-(4000/6))<0.01);
const purchaseCount=financeDB.purchases.length,stockBefore=financeDB.variants[0].stock;
assert.throws(()=>engine.createPurchase({
  items:[{variantId:'v1',qty:1,unitPrice:1000}],
  payments:{cash:500,card:0,bank:0,credit:0},warehouseId:'W2'
}));
assert.strictEqual(financeDB.purchases.length,purchaseCount);
assert.strictEqual(financeDB.variants[0].stock,stockBefore);
const journalsBalanced=financeDB.journal.every(j=>Math.abs(j.debit-j.credit)<0.01);
assert.strictEqual(journalsBalanced,true);
console.log('extracted engine scenarios: VAT purchase/sale, warehouse returns, migrated weighted cost, mismatch rollback — PASS');
