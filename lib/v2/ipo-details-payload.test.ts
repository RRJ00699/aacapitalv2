import test from "node:test"; import assert from "node:assert/strict";
import {assertDetailsPayloadSizes,measureDetailsPayloads} from "./details-payload";
test("measurement reports distribution without truncating payload",()=>{const p=[{name:"ipo-details:isin:INE000000001:v1",payload:{verified_evidence:["a","b"]}},{name:"ipo-details:isin:INE000000002:v1",payload:{verified_evidence:["x"]}}];const {measured,report}=measureDetailsPayloads(p);assert.equal(report.count,2);assert.equal((measured.find(x=>x.isin==="INE000000001")!.payload as any).verified_evidence.length,2)});
test("oversize error names ISIN, actual bytes and maximum",()=>{assert.throws(()=>assertDetailsPayloadSizes([{isin:"INE000000001",bytes:101}],100),/ISIN=INE000000001 actual_bytes=101 configured_max=100/)});
