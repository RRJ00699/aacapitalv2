// AI Provider Abstraction
// Switch providers by setting AI_PROVIDER env variable
// Options: "anthropic" | "openai" | "gemini"
// Default: anthropic

type AIProvider = "anthropic" | "openai" | "gemini"

function getProvider(): AIProvider {
  const p = process.env.AI_PROVIDER as AIProvider
  return p || "anthropic"
}

interface AIMessage { role: "user" | "assistant"; content: string }

interface AICallOptions {
  messages: AIMessage[]
  maxTokens?: number
  webSearch?: boolean
}

export async function callAI(options: AICallOptions): Promise<string> {
  const provider = getProvider()
  const { messages, maxTokens = 1800, webSearch = false } = options

  if (provider === "openai") {
    const res = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${process.env.OPENAI_API_KEY}`,
      },
      body: JSON.stringify({
        model: process.env.OPENAI_MODEL || "gpt-4o",
        max_tokens: maxTokens,
        messages,
      }),
    })
    if (!res.ok) throw new Error(`OpenAI error: ${res.status}`)
    const json = await res.json()
    return json.choices?.[0]?.message?.content || ""
  }

  if (provider === "gemini") {
    const res = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key=${process.env.GEMINI_API_KEY}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          contents: messages.map(m => ({
            role: m.role === "user" ? "user" : "model",
            parts: [{ text: m.content }],
          })),
          generationConfig: { maxOutputTokens: maxTokens },
        }),
      }
    )
    if (!res.ok) throw new Error(`Gemini error: ${res.status}`)
    const json = await res.json()
    return json.candidates?.[0]?.content?.parts?.[0]?.text || ""
  }

  // Default: Anthropic
  const body: any = {
    model: process.env.ANTHROPIC_MODEL || "claude-sonnet-4-20250514",
    max_tokens: maxTokens,
    messages,
  }
  if (webSearch) {
    body.tools = [{ type: "web_search_20250305", name: "web_search" }]
  }
  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": process.env.ANTHROPIC_API_KEY || "",
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`Anthropic error: ${res.status}`)
  const json = await res.json()
  // Handle both text and web search responses
  const textBlock = json.content?.find((b: any) => b.type === "text")
  return textBlock?.text || json.content?.[0]?.text || ""
}
