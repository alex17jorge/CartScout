import { useState } from 'react'
import './App.css'

const initialMessages = [
  {
    id: 1,
    role: 'assistant',
    text: 'Hi! Ask me about champions, items, game systems, or anything else that changed in the latest patches.',
  },
]

function SendIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="m5 12 14-7-4 14-3-6-7-1Z" />
      <path d="m12 13 7-8" />
    </svg>
  )
}

function App() {
  const [messages, setMessages] = useState(initialMessages)
  const [draft, setDraft] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(event) {
    event.preventDefault()

    const message = draft.trim()
    if (!message || isLoading) return

    const userMessage = { id: Date.now(), role: 'user', text: message }
    const history = messages.map(({ role, text }) => ({ role, content: text }))

    setMessages((currentMessages) => [...currentMessages, userMessage])
    setDraft('')
    setError('')
    setIsLoading(true)

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, history }),
      })
      const data = await response.json()

      if (!response.ok) {
        throw new Error(data.detail || 'The assistant could not answer.')
      }

      setMessages((currentMessages) => [
        ...currentMessages,
        { id: `${Date.now()}-assistant`, role: 'assistant', text: data.answer },
      ])
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <main className="app-shell">
      <header className="site-header">
        <h1>Patch Notes Buddy</h1>
      </header>

      <section className="chat" aria-label="Patch notes chat">
        <div className="messages" aria-live="polite">
          {messages.map((message) => (
            <article className={`message message--${message.role}`} key={message.id}>
              <span className="message-label">
                {message.role === 'assistant' ? 'Buddy' : 'You'}
              </span>
              <p>{message.text}</p>
            </article>
          ))}
          {isLoading && (
            <article className="message message--assistant">
              <span className="message-label">Buddy</span>
              <p className="loading-message">Thinking…</p>
            </article>
          )}
        </div>

        <form className="composer" onSubmit={handleSubmit}>
          <label className="sr-only" htmlFor="chat-message">
            Ask about a patch
          </label>
          <input
            id="chat-message"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Ask what changed in patch 26.14..."
            autoComplete="off"
            disabled={isLoading}
          />
          <button
            type="submit"
            disabled={!draft.trim() || isLoading}
            aria-label="Send message"
          >
            <SendIcon />
          </button>
        </form>
        {error && <p className="error-message" role="alert">{error}</p>}
      </section>
    </main>
  )
}

export default App
