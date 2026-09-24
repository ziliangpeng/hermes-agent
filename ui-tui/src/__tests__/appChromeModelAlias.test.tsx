import React from 'react'
import { describe, expect, it } from 'vitest'

import { StatusRule } from '../components/appChrome.js'
import { DEFAULT_THEME } from '../theme.js'

type ReactNodeLike = React.ReactNode

const textContent = (node: ReactNodeLike): string => {
  if (node === null || node === undefined || typeof node === 'boolean') {
    return ''
  }
  if (typeof node === 'string' || typeof node === 'number') {
    return String(node)
  }
  if (Array.isArray(node)) {
    return node.map(textContent).join('')
  }
  if (React.isValidElement(node)) {
    return textContent(node.props.children)
  }
  return ''
}

const baseProps = {
  bgCount: 0,
  busy: false,
  cols: 100,
  cwdLabel: '~/repo',
  liveSessionCount: 0,
  model: 'some-long-model-id-v2-fp8',
  sessionStartedAt: null,
  status: 'ready',
  statusColor: DEFAULT_THEME.color.ok,
  t: DEFAULT_THEME,
  turnStartedAt: null,
  usage: { context_max: 200_000, context_percent: 25, context_used: 50_000, total: 50_000 },
  voiceLabel: ''
}

describe('StatusRule model alias (session.info model_alias)', () => {
  it('renders the gateway-provided alias instead of the generic label', () => {
    const out = textContent(StatusRule({ ...baseProps, modelAlias: 'm2' }))
    expect(out).toContain('m2')
    expect(out).not.toContain('some long model id')
  })

  it('falls back to the generic short label when no alias is set', () => {
    const out = textContent(StatusRule({ ...baseProps }))
    expect(out).toContain('some long model id v2 fp8')
  })

  it('keeps the effort suffix next to the alias', () => {
    const out = textContent(
      StatusRule({ ...baseProps, modelAlias: 'm2', modelReasoningEffort: 'high' })
    )
    expect(out).toContain('m2 high')
  })
})
