// app/ipo/page.tsx — nav lands here; forwards to the live IPO page.
// CUTOVER SWITCH: change the target to "/dashboard/ipo2" to go live on the redesign.
import { redirect } from "next/navigation";
export default function IpoRedirect() { redirect("/dashboard/ipo"); }
