import { createContext, useContext } from 'react'

export const SessionContext = createContext(null)

export function useSession() {
  const context = useContext(SessionContext)
  if (!context) throw new Error('useSession must be used inside SessionProvider')
  return context
}
