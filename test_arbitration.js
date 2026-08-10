// Integration test fixture for Freelance Arbitration contract on Bradbury testnet.
// Covers: create_contract (escrow) → submit_evidence → raise_dispute → adjudicate → claim_funds
// Read flow: get_stats, get_contract, list_contracts
// Run: node test_arbitration.js <contract_id>
const CONTRACT = '0x3B6b02ea05F6c26157D305c6E7AE690F5E1796F2';
const RPC = 'https://rpc-bradbury.genlayer.com';

async function genCall(method, args) {
  const res = await fetch(RPC, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'gen_call', params: [{ to: CONTRACT, function: method, args: args }] })
  });
  const data = await res.json();
  if (data.error) throw new Error(data.error.message || JSON.stringify(data.error));
  return data.result;
}

async function main() {
  const contractId = process.argv[2] || '1';

  console.log('=== 1. get_stats() ===');
  const stats = await genCall('get_stats', []);
  console.log(JSON.stringify(stats, null, 2));

  console.log(`\n=== 2. get_contract("${contractId}") ===`);
  const c = await genCall('get_contract', [contractId]);
  console.log(JSON.stringify(c, null, 2));

  console.log(`\n=== 3. get_contract_balance() ===`);
  const balance = await genCall('get_contract_balance', []);
  console.log(balance);

  console.log(`\n=== 4. list_contracts() ===`);
  const list = await genCall('list_contracts', []);
  console.log(JSON.stringify(list, null, 2));

  console.log(`\n=== Note ===`);
  console.log('Write transactions (via MetaMask in the dApp or genlayer CLI):');
  console.log('  create_contract  : payable, sends GEN into escrow');
  console.log('  submit_evidence  : parties submit evidence URLs independently');
  console.log('  raise_dispute    : escalate to AI arbitration');
  console.log('  adjudicate       : AI validators reach consensus verdict + split %');
  console.log('  claim_funds      : release/refund based on consensus split');
}

main().catch(e => { console.error('FAILED:', e.message); process.exit(1); });
