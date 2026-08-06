export function measureDetailsPayloads(details: Array<{name:string,payload:unknown}>) {
  const measured = details.map(item => ({ ...item, isin: item.name.split(":")[2], bytes: Buffer.byteLength(JSON.stringify(item.payload)) })).sort((a,b)=>a.bytes-b.bytes);
  const sizes=measured.map(x=>x.bytes); const count=sizes.length;
  return { measured, report: { count, median_bytes:count?sizes[Math.floor((count-1)/2)]:0, p95_bytes:count?sizes[Math.ceil(count*.95)-1]:0, maximum_bytes:count?sizes[count-1]:0, largest_isin:count?measured[count-1].isin:null, total_bytes_selected:sizes.reduce((a,b)=>a+b,0), projected_total_bytes_50:count?Math.round(sizes.reduce((a,b)=>a+b,0)/count*50):0 } };
}
export function assertDetailsPayloadSizes(measured: Array<{isin:string,bytes:number}>, maximum:number) {
  for(const item of measured) if(item.bytes>maximum) throw new Error(`details payload oversized: ISIN=${item.isin} actual_bytes=${item.bytes} configured_max=${maximum}`);
}
