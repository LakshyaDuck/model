import { useState } from 'react'
import { copyText } from '../../lib/clipboard.js'
import Button from './Button.jsx'

export default function CopyButton({
  value,
  label = 'Copy',
  copiedLabel = 'Copied',
  errorLabel = 'Copy failed',
  variant = 'secondary',
  size = 'sm',
  className = '',
}) {
  const [state, setState] = useState('idle')

  const handleCopy = async () => {
    try {
      await copyText(value)
      setState('copied')
    } catch {
      setState('error')
    }
    window.setTimeout(() => setState('idle'), 2000)
  }

  return (
    <Button
      variant={variant}
      size={size}
      onClick={handleCopy}
      className={className}
      aria-live="polite"
    >
      {state === 'copied' ? copiedLabel : state === 'error' ? errorLabel : label}
    </Button>
  )
}
