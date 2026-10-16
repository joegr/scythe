import { createContext, useContext } from 'react'
import type { GhUser } from './gh'

export const SessionContext = createContext<GhUser | null>(null)
/** Signed in = a GitHub token that can write this repo's issues. Reading needs nothing. */
export const useSignedIn = () => useContext(SessionContext) !== null
export const useUser = () => useContext(SessionContext)
