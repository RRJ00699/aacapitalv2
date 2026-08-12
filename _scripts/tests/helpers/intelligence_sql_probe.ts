import postgres from "postgres";
import { fetchDetailsRows,detailsFromRow } from "../../../lib/v2/ipo-details";
import type { SqlClient } from "../../../lib/v2/sql";

async function main() {
 const sql=process.env.PGHOST
  ? postgres({
      host:process.env.PGHOST,
      ...(process.env.PGPORT?{port:Number(process.env.PGPORT)}:{}),
      database:process.env.PGDATABASE,
      username:process.env.PGUSER,
      password:process.env.PGPASSWORD,
      max:1,
    })
  : postgres(process.env.DATABASE_URL!,{max:1});
 try {
  const rows=await fetchDetailsRows(sql as unknown as SqlClient,[1]);
  const details=detailsFromRow(rows[0],"2026-08-07T00:00:00Z");
  const profile=details.intelligence_profile as any;
  process.stdout.write(JSON.stringify({status:profile?.valuation?.status??null,
    post_issue_shares_cr:profile?.valuation?.post_issue_shares_cr??null,
    cash_cr:profile?.valuation?.cash_cr??null,
    financial_basis:profile?.provenance?.pro_forma_inputs?.financial_basis??null}));
 } finally { await sql.end(); }
}
main().catch((error) => { console.error(error); process.exitCode=1; });
