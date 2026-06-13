import { cookies } from "next/headers"
import { getDb } from "@/lib/db/schema"

export type UserRole =
  | "OWNER"
  | "FAMILY_VIEW"
  | "TRUSTED_PERSON"
  | "EMPLOYEE_L1"
  | "EMPLOYEE_L2"

export interface AuthUser {
  id: number
  email: string
  name: string
  role: UserRole
  tradeLimit: number
}

export const ROLE_PERMISSIONS: Record<UserRole, {
  canTrade: boolean
  canSeePortfolio: boolean
  canSeeResearch: boolean
  canSubmitResearch: boolean
  tradeLimit: number
}> = {
  OWNER:          { canTrade: true,  canSeePortfolio: true,  canSeeResearch: true,  canSubmitResearch: true,  tradeLimit: Infinity },
  FAMILY_VIEW:    { canTrade: false, canSeePortfolio: true,  canSeeResearch: false, canSubmitResearch: false, tradeLimit: 0 },
  TRUSTED_PERSON: { canTrade: false, canSeePortfolio: false, canSeeResearch: true,  canSubmitResearch: false, tradeLimit: 0 },
  EMPLOYEE_L1:    { canTrade: false, canSeePortfolio: false, canSeeResearch: true,  canSubmitResearch: true,  tradeLimit: 0 },
  EMPLOYEE_L2:    { canTrade: true,  canSeePortfolio: false, canSeeResearch: true,  canSubmitResearch: true,  tradeLimit: 1000000 },
}

export async function getCurrentUser(): Promise<AuthUser | null> {
  try {
    const cookieStore = await cookies()
    const sessionId = cookieStore.get("session")?.value
    if (!sessionId) return null

    const sql = getDb()
    const rows = await sql`
      SELECT u.id, u.email, u.name, u.role, u.trade_limit
      FROM users u
      JOIN user_sessions s ON s.user_id = u.id
      WHERE s.session_id = ${sessionId}
        AND s.expires_at > NOW()
    `
    if (!rows[0]) return null
    return {
      id: rows[0].id,
      email: rows[0].email,
      name: rows[0].name,
      role: rows[0].role as UserRole,
      tradeLimit: rows[0].trade_limit,
    }
  } catch { return null }
}

export async function requireAuth(): Promise<AuthUser> {
  const user = await getCurrentUser()
  if (!user) throw new Error("Unauthorized")
  return user
}

export async function requireOwner(): Promise<AuthUser> {
  const user = await requireAuth()
  if (user.role !== "OWNER") throw new Error("Forbidden — Owner only")
  return user
}
