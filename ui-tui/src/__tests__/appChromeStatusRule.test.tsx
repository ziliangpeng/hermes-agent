import React from 'react'
import { describe, expect, it, vi } from 'vitest'

import { StatusRule, statusRuleWidths, statusBarSegments, ctxBarColor, ctxBarHalf, memoryProfileLabel, skillsLabel } from '../components/appChrome.js'
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

const findClickableWithText = (node: ReactNodeLike, needle: string): React.ReactElement | null => {
  if (node === null || node === undefined || typeof node === 'boolean') {
    return null
  }

  if (Array.isArray(node)) {
    for (const child of node) {
      const found = findClickableWithText(child, needle)

      if (found) {
        return found
      }
    }

    return null
  }

  if (!React.isValidElement(node)) {
    return null
  }

  if (typeof node.props.onClick === 'function' && textContent(node).includes(needle)) {
    return node
  }

  return findClickableWithText(node.props.children, needle)
}

// Find the innermost element whose own (direct) text content includes the
// needle. Used to assert the colour the notice text is rendered with.
const findElementWithText = (node: ReactNodeLike, needle: string): React.ReactElement | null => {
  if (node === null || node === undefined || typeof node === 'boolean') {
    return null
  }

  if (Array.isArray(node)) {
    for (const child of node) {
      const found = findElementWithText(child, needle)

      if (found) {
        return found
      }
    }

    return null
  }

  if (!React.isValidElement(node)) {
    return null
  }

  // Prefer the deepest matching element so we get the leaf <Text> that
  // actually carries the colour, not an ancestor Box.
  const deeper = findElementWithText(node.props.children, needle)

  if (deeper) {
    return deeper
  }

  return textContent(node).includes(needle) ? node : null
}

const baseProps = {
  bgCount: 0,
  busy: false,
  cols: 100,
  cwdLabel: '~/repo',
  liveSessionCount: 0,
  model: 'opus-4.8',
  sessionStartedAt: null,
  status: 'ready',
  statusColor: DEFAULT_THEME.color.ok,
  t: DEFAULT_THEME,
  turnStartedAt: null,
  usage: { context_max: 200_000, context_percent: 25, context_used: 50_000, total: 50_000 },
  voiceLabel: ''
}

describe('StatusRule background-subagent indicator', () => {
  it('renders 🏃N on a wide terminal when subagents are running', () => {
    const element = StatusRule({
      ...baseProps,
      usage: { ...baseProps.usage, active_subagents: 3 }
    })

    expect(textContent(element)).toContain('🏃3')
  })

  it('renders 🏃N🏁M when subagents are running and some completed', () => {
    const element = StatusRule({
      ...baseProps,
      usage: { ...baseProps.usage, active_subagents: 3, completed_subagents: 2 }
    })

    expect(textContent(element)).toContain('🏃3🏁2')
  })

  it('renders 🏃N without 🏁 when completed_subagents is 0', () => {
    const element = StatusRule({
      ...baseProps,
      usage: { ...baseProps.usage, active_subagents: 3, completed_subagents: 0 }
    })

    expect(textContent(element)).toContain('🏃3')
    expect(textContent(element)).not.toContain('🏁')
  })

  it('omits the segment when no subagents are running', () => {
    const element = StatusRule({
      ...baseProps,
      usage: { ...baseProps.usage, active_subagents: 0 }
    })

    expect(textContent(element)).not.toContain('🏃')
  })

  it('omits the segment when the field is absent', () => {
    const element = StatusRule({ ...baseProps })

    expect(textContent(element)).not.toContain('🏃')
  })

  it('shows the ↩ resume hint when idle with subagents in flight', () => {
    const element = StatusRule({
      ...baseProps,
      usage: { ...baseProps.usage, active_subagents: 3 }
    })

    expect(textContent(element)).toContain('↩')
  })

  it('hides the resume hint mid-turn (a busy turn owns the indicator)', () => {
    const element = StatusRule({
      ...baseProps,
      busy: true,
      turnStartedAt: Date.now(),
      usage: { ...baseProps.usage, active_subagents: 2 }
    })

    expect(textContent(element)).not.toContain('↩')
  })

  it('omits the resume hint when no subagents are running', () => {
    const element = StatusRule({ ...baseProps })

    expect(textContent(element)).not.toContain('↩')
  })

  it('keeps the subagent segment on a narrow terminal (pinned before model)', () => {
    // Subagent indicator is now pinned (part of essentialWidth), so it
    // survives even at cols=44 when subagents are running.
    const element = StatusRule({
      ...baseProps,
      cols: 44,
      bgCount: 1,
      usage: { ...baseProps.usage, active_subagents: 2 }
    })

    expect(textContent(element)).toContain('🏃')
  })
})

describe('StatusRule voice label', () => {
  it('hides the voice segment when voiceLabel is empty (off)', () => {
    const element = StatusRule({ ...baseProps, voiceLabel: '' })
    expect(textContent(element)).not.toContain('🎤')
    expect(textContent(element)).not.toContain('📢')
    expect(textContent(element)).not.toContain('🔴')
    expect(textContent(element)).not.toContain('🟡')
  })

  it('shows 🎤 when voice is on', () => {
    const element = StatusRule({ ...baseProps, voiceLabel: '🎤' })
    expect(textContent(element)).toContain('🎤')
  })

  it('shows 📢 when voice is on with TTS', () => {
    const element = StatusRule({ ...baseProps, voiceLabel: '📢' })
    expect(textContent(element)).toContain('📢')
  })

  it('shows 🔴 when recording', () => {
    const element = StatusRule({ ...baseProps, voiceLabel: '🔴' })
    expect(textContent(element)).toContain('🔴')
  })

  it('shows 🟡 when STT is processing', () => {
    const element = StatusRule({ ...baseProps, voiceLabel: '🟡' })
    expect(textContent(element)).toContain('🟡')
  })
})

describe('StatusRule context progress bar', () => {
  it('renders bar and percentage when context_max is set', () => {
    const element = StatusRule({ ...baseProps, usage: { ...baseProps.usage, context_percent: 50 } })
    const rendered = textContent(element)
    expect(rendered).toContain('█')
    expect(rendered).toContain('░')
    expect(rendered).toContain('50%')
  })

  it('shows at least one filled cell at 5% (visibility fix)', () => {
    const element = StatusRule({ ...baseProps, usage: { ...baseProps.usage, context_percent: 5 } })
    const rendered = textContent(element)
    expect(rendered).toContain('▌')
    expect(rendered).toContain('5%')
  })

  it('shows full bar at 95%', () => {
    const element = StatusRule({ ...baseProps, usage: { ...baseProps.usage, context_percent: 95 } })
    const rendered = textContent(element)
    expect(rendered).toContain('████')
    expect(rendered).toContain('95%')
  })

  it('omits bar in compact context mode', () => {
    const element = StatusRule({ ...baseProps, cols: 60 })
    const rendered = textContent(element)
    expect(rendered).not.toContain('█')
    expect(rendered).not.toContain('░')
  })
})

describe('StatusRule session count click target', () => {
  it('makes the live session count itself clickable', () => {
    const openSwitcher = vi.fn()

    const element = StatusRule({
      bgCount: 0,
      busy: false,
      cols: 100,
      cwdLabel: '~/repo',
      liveSessionCount: 2,
      model: 'kimi-k2.6',
      onSessionCountClick: openSwitcher,
      sessionStartedAt: null,
      status: 'ready',
      statusColor: DEFAULT_THEME.color.ok,
      t: DEFAULT_THEME,
      turnStartedAt: null,
      usage: { total: 0 },
      voiceLabel: ''
    })

    const clickableSessionCount = findClickableWithText(element, '2 sessions')

    expect(clickableSessionCount).not.toBeNull()
    clickableSessionCount!.props.onClick({ stopImmediatePropagation: vi.fn() })
    expect(openSwitcher).toHaveBeenCalledOnce()
  })

  it('self-hides when only 1 active session', () => {
    const element = StatusRule({
      ...baseProps,
      liveSessionCount: 1,
      onSessionCountClick: vi.fn()
    })

    expect(textContent(element)).not.toContain('1 session')
  })

  it('keeps status + model and drops the low-value tail on a narrow terminal', () => {
    const element = StatusRule({
      bgCount: 0,
      busy: false,
      cols: 44,
      cwdLabel: '~/src/hermes-agent/apps/desktop (bb/tui-statusbar-responsive)',
      liveSessionCount: 3,
      model: 'opus-4.8',
      onSessionCountClick: vi.fn(),
      sessionStartedAt: Date.now() - 60_000,
      status: 'ready',
      statusColor: DEFAULT_THEME.color.ok,
      t: DEFAULT_THEME,
      turnStartedAt: null,
      usage: {
        calls: 0,
        context_max: 200_000,
        context_percent: 25,
        context_used: 50_000,
        input: 0,
        output: 0,
        total: 50_000
      },
      voiceLabel: ''
    })

    const rendered = textContent(element)

    // Must-keep essentials survive intact …
    expect(rendered).toContain('ready')
    expect(rendered).toContain('o4.8')
    // … while the low-value tail (session count) is dropped, not truncated.
    expect(rendered).not.toContain('3 sessions')
  })
})

describe('StatusRule credits notice render priority', () => {
  it('replaces the idle status with the notice text and keeps model + context', () => {
    const element = StatusRule({
      ...baseProps,
      notice: { key: 'credits.depleted', kind: 'sticky', level: 'error', text: '✕ credits exhausted' }
    })

    const rendered = textContent(element)

    // Notice replaces the status verb slot …
    expect(rendered).toContain('✕ credits exhausted')
    expect(rendered).not.toContain('ready')
    // … but model + context stay visible.
    expect(rendered).toContain('o4.8')
    expect(rendered).toContain('50k')
  })

  it('busy wins: the FaceTicker shows, the notice is hidden mid-turn', () => {
    const element = StatusRule({
      ...baseProps,
      busy: true,
      notice: { key: 'credits.90', kind: 'sticky', level: 'warn', text: '⚠ 90% used' },
      turnStartedAt: Date.now()
    })

    const rendered = textContent(element)

    // Notice must NOT render while busy.
    expect(rendered).not.toContain('⚠ 90% used')
    // Model still visible.
    expect(rendered).toContain('o4.8')
  })

  it('colours the notice by level (error → theme error, success → statusGood)', () => {
    const errEl = StatusRule({
      ...baseProps,
      notice: { key: 'credits.depleted', kind: 'sticky', level: 'error', text: '✕ exhausted' }
    })

    const errText = findElementWithText(errEl, '✕ exhausted')
    expect(errText?.props.color).toBe(DEFAULT_THEME.color.error)

    const okEl = StatusRule({
      ...baseProps,
      notice: { key: 'credits.restored', kind: 'ttl', level: 'success', text: '✓ restored', ttl_ms: 8000 }
    })

    const okText = findElementWithText(okEl, '✓ restored')
    expect(okText?.props.color).toBe(DEFAULT_THEME.color.statusGood)
  })

  it('does NOT add a glyph — the notice text is rendered verbatim', () => {
    const element = StatusRule({
      ...baseProps,
      notice: { key: 'credits.90', kind: 'sticky', level: 'warn', text: '⚠ 90% used' }
    })

    const noticeText = findElementWithText(element, '90% used')

    // The leaf carries exactly the policy text — no extra prepended glyph.
    expect(noticeText?.props.children).toBe('⚠ 90% used')
  })

  it('the notice text is the shrinkable element (flexShrink=1 + truncate-end) so a long notice ellipsizes', () => {
    const longText = '⚠ ' + 'x'.repeat(200)

    const element = StatusRule({
      ...baseProps,
      cols: 50,
      notice: { key: 'credits.90', kind: 'sticky', level: 'warn', text: longText }
    })

    // The leaf <Text> truncates rather than wrapping/clipping the pinned tail.
    const noticeText = findElementWithText(element, 'xxxxx')
    expect(noticeText?.props.wrap).toBe('truncate-end')

    // Its container box yields first (flexShrink=1) so model stays visible.
    const findShrinkBoxContaining = (node: ReactNodeLike): React.ReactElement | null => {
      if (!React.isValidElement(node)) {
        if (Array.isArray(node)) {
          for (const c of node) {
            const f = findShrinkBoxContaining(c)

            if (f) {
              return f
            }
          }
        }

        return null
      }

      if (node.props.flexShrink === 1 && textContent(node).includes('xxxxx') && node.type !== StatusRule) {
        // Prefer the closest shrink box that wraps the notice text.
        const deeper = findShrinkBoxContaining(node.props.children)

        return deeper ?? node
      }

      return findShrinkBoxContaining(node.props.children)
    }

    const shrinkBox = findShrinkBoxContaining(element)
    expect(shrinkBox).not.toBeNull()

    // Model survives on a narrow terminal because the notice yields.
    expect(textContent(element)).toContain('o4.8')
  })
})

describe('StatusRule idle-since read-out', () => {
  // The IdleSince component uses hooks, so it can't be invoked outside a
  // renderer — assert on the element tree instead.  The idle clock now lives
  // inside the status slot (`🔥 ready 5m`) rather than as a standalone tail
  // segment, so IdleSince is found as a child of the status <Text>.
  const findComponentByName = (node: ReactNodeLike, name: string): React.ReactElement | null => {
    if (node === null || node === undefined || typeof node === 'boolean') {
      return null
    }

    if (Array.isArray(node)) {
      for (const child of node) {
        const found = findComponentByName(child, name)

        if (found) {
          return found
        }
      }

      return null
    }

    if (!React.isValidElement(node)) {
      return null
    }

    if (typeof node.type === 'function' && node.type.name === name) {
      return node
    }

    return findComponentByName(node.props.children, name)
  }

  it('shows time since the last final agent response when idle', () => {
    const endedAt = Date.now() - 42_000

    const element = StatusRule({
      ...baseProps,
      lastTurnEndedAt: endedAt,
      sessionStartedAt: Date.now() - 60_000
    })

    const idle = findComponentByName(element, 'IdleSince')

    expect(idle).not.toBeNull()
    expect(idle!.props.endedAt).toBe(endedAt)
    // Idle clock lives in the status slot now (🔥 ready 42s), not a standalone
    // segment — ✓ glyph must be gone.
    const rendered = textContent(element)
    expect(rendered).not.toContain('✓')
    expect(rendered).toContain('ready')
  })

  it('is hidden while a turn is busy', () => {
    const element = StatusRule({
      ...baseProps,
      busy: true,
      lastTurnEndedAt: Date.now() - 42_000,
      turnStartedAt: Date.now()
    })

    expect(findComponentByName(element, 'IdleSince')).toBeNull()
  })

  it('is hidden before the first turn completes', () => {
    const element = StatusRule({
      ...baseProps,
      lastTurnEndedAt: null,
      sessionStartedAt: Date.now() - 60_000
    })

    expect(findComponentByName(element, 'IdleSince')).toBeNull()
  })
})

// ── P0a: Pure function tests ──────────────────────────────────────────

describe('statusBarSegments', () => {
  it('enables all segments at 100 cols', () => {
    const segs = statusBarSegments(100)
    expect(segs.bar).toBe(true)
    expect(segs.duration).toBe(true)
    expect(segs.compressions).toBe(true)
    expect(segs.voice).toBe(true)
    expect(segs.bg).toBe(true)
    expect(segs.subagents).toBe(true)
    expect(segs.compactCtx).toBe(false)
  })

  it('enables compactCtx below 72 cols', () => {
    expect(statusBarSegments(71).compactCtx).toBe(true)
    expect(statusBarSegments(72).compactCtx).toBe(false)
  })

  it('enables bar at 72 cols', () => {
    expect(statusBarSegments(71).bar).toBe(false)
    expect(statusBarSegments(72).bar).toBe(true)
  })

  it('enables duration at 76 cols', () => {
    expect(statusBarSegments(75).duration).toBe(false)
    expect(statusBarSegments(76).duration).toBe(true)
  })

  it('enables compressions at 80 cols', () => {
    expect(statusBarSegments(79).compressions).toBe(false)
    expect(statusBarSegments(80).compressions).toBe(true)
  })

  it('enables voice at 84 cols', () => {
    expect(statusBarSegments(83).voice).toBe(false)
    expect(statusBarSegments(84).voice).toBe(true)
  })

  it('enables bg at 88 cols', () => {
    expect(statusBarSegments(87).bg).toBe(false)
    expect(statusBarSegments(88).bg).toBe(true)
  })

  it('enables subagents at 92 cols', () => {
    expect(statusBarSegments(91).subagents).toBe(false)
    expect(statusBarSegments(92).subagents).toBe(true)
  })

  it('disables all tail segments at 44 cols', () => {
    const segs = statusBarSegments(44)
    expect(segs.bar).toBe(false)
    expect(segs.duration).toBe(false)
    expect(segs.compressions).toBe(false)
    expect(segs.voice).toBe(false)
    expect(segs.bg).toBe(false)
    expect(segs.subagents).toBe(false)
    expect(segs.compactCtx).toBe(true)
  })
})

describe('statusRuleWidths', () => {
  it('returns full width as leftWidth when cwdLabel is empty', () => {
    const { leftWidth, rightWidth, separatorWidth } = statusRuleWidths(100, '')
    expect(leftWidth).toBe(100)
    expect(rightWidth).toBe(0)
    expect(separatorWidth).toBe(0)
  })

  it('splits width between left and right when cwdLabel is set', () => {
    const { leftWidth, rightWidth, separatorWidth } = statusRuleWidths(100, '~/repo')
    expect(separatorWidth).toBe(3)
    expect(rightWidth).toBe(6) // stringWidth('~/repo') = 6
    expect(leftWidth).toBe(91) // 100 - 3 - 6
  })

  it('uses 1-col separator below 24 cols', () => {
    const { separatorWidth } = statusRuleWidths(20, '~/r')
    expect(separatorWidth).toBe(1)
  })

  it('respects minLeftContent', () => {
    const { leftWidth, rightWidth } = statusRuleWidths(50, '~/very/long/path', 40)
    expect(leftWidth).toBeGreaterThanOrEqual(40)
    expect(rightWidth).toBeGreaterThan(0)
  })

  it('gives minimal rightWidth when terminal is very narrow', () => {
    const { leftWidth, rightWidth } = statusRuleWidths(10, '~/very/long/path', 8)
    expect(leftWidth).toBeGreaterThanOrEqual(8)
    expect(rightWidth).toBeLessThanOrEqual(2)
  })
})

// ── P0b: SessionDuration segment ──────────────────────────────────────

describe('StatusRule session duration', () => {
  it('shows session duration when sessionStartedAt is set', () => {
    const element = StatusRule({
      ...baseProps,
      sessionStartedAt: Date.now() - 5 * 60_000
    })
    // SessionDuration uses hooks — verify the component is present in tree
    const findComp = (node: ReactNodeLike): any => {
      if (!node || typeof node !== 'object') return null
      if ((node as any).type?.name === 'SessionDuration') return node
      const children = (node as any).props?.children
      if (Array.isArray(children)) {
        for (const c of children) {
          const found = findComp(c)
          if (found) return found
        }
      } else if (children) {
        return findComp(children)
      }
      return null
    }
    expect(findComp(element)).not.toBeNull()
  })

  it('hides duration when sessionStartedAt is null', () => {
    const element = StatusRule({ ...baseProps, sessionStartedAt: null })
    // SessionDuration component should not be in the tree
    const findComp = (node: ReactNodeLike): any => {
      if (!node || typeof node !== 'object') return null
      if ((node as any).type?.name === 'SessionDuration') return node
      const children = (node as any).props?.children
      if (Array.isArray(children)) {
        for (const c of children) {
          const found = findComp(c)
          if (found) return found
        }
      } else if (children) {
        return findComp(children)
      }
      return null
    }
    expect(findComp(element)).toBeNull()
  })
})

// ── P0c: Compressions segment ─────────────────────────────────────────

describe('StatusRule compressions', () => {
  it('shows compression count when compressions > 0', () => {
    const element = StatusRule({
      ...baseProps,
      usage: { ...baseProps.usage, compressions: 3 }
    })
    expect(textContent(element)).toContain('cmp 3')
  })

  it('hides compressions when count is 0', () => {
    const element = StatusRule({
      ...baseProps,
      usage: { ...baseProps.usage, compressions: 0 }
    })
    expect(textContent(element)).not.toContain('cmp')
  })

  it('shows compressions at warn threshold (5)', () => {
    const element = StatusRule({
      ...baseProps,
      usage: { ...baseProps.usage, compressions: 5 }
    })
    const cmpEl = findElementWithText(element, 'cmp 5')
    expect(cmpEl).not.toBeNull()
    expect(cmpEl?.props.color).toBe(DEFAULT_THEME.color.warn)
  })

  it('shows compressions at error threshold (10)', () => {
    const element = StatusRule({
      ...baseProps,
      usage: { ...baseProps.usage, compressions: 10 }
    })
    const cmpEl = findElementWithText(element, 'cmp 10')
    expect(cmpEl).not.toBeNull()
    expect(cmpEl?.props.color).toBe(DEFAULT_THEME.color.error)
  })
})

// ── P0d: memSkl segment ───────────────────────────────────────────────

describe('memoryProfileLabel', () => {
  it('shows memory and user percentages', () => {
    const label = memoryProfileLabel({ memory_chars: 10000, memory_limit: 50000, user_chars: 5000, user_limit: 10000 })
    expect(label).toBe('M20% U50%')
  })

  it('shows only memory when user data is missing', () => {
    const label = memoryProfileLabel({ memory_chars: 10000, memory_limit: 50000 })
    expect(label).toBe('M20%')
  })

  it('returns empty string when no data', () => {
    expect(memoryProfileLabel({})).toBe('')
  })
})

describe('skillsLabel', () => {
  it('shows skill count', () => {
    expect(skillsLabel({ skill_count: 165 })).toBe('S165')
  })

  it('returns empty string when skill_count is missing', () => {
    expect(skillsLabel({})).toBe('')
  })
})

describe('StatusRule memSkl segment', () => {
  it('shows memory and skill labels', () => {
    const element = StatusRule({
      ...baseProps,
      usage: {
        ...baseProps.usage,
        memory_chars: 10000,
        memory_limit: 50000,
        user_chars: 5000,
        user_limit: 10000,
        skill_count: 42
      }
    })
    const rendered = textContent(element)
    expect(rendered).toContain('M20%')
    expect(rendered).toContain('U50%')
    expect(rendered).toContain('S42')
  })
})

// ── P2: Color threshold tests ─────────────────────────────────────────

describe('ctxBarColor', () => {
  it('returns statusGood below 50%', () => {
    expect(ctxBarColor(25, DEFAULT_THEME)).toBe(DEFAULT_THEME.color.statusGood)
  })

  it('returns statusWarn at 50-80%', () => {
    expect(ctxBarColor(50, DEFAULT_THEME)).toBe(DEFAULT_THEME.color.statusWarn)
    expect(ctxBarColor(79, DEFAULT_THEME)).toBe(DEFAULT_THEME.color.statusWarn)
  })

  it('returns statusBad at >80% to <95%', () => {
    expect(ctxBarColor(81, DEFAULT_THEME)).toBe(DEFAULT_THEME.color.statusBad)
    expect(ctxBarColor(94, DEFAULT_THEME)).toBe(DEFAULT_THEME.color.statusBad)
  })

  it('returns statusCritical at 95%+', () => {
    expect(ctxBarColor(95, DEFAULT_THEME)).toBe(DEFAULT_THEME.color.statusCritical)
    expect(ctxBarColor(100, DEFAULT_THEME)).toBe(DEFAULT_THEME.color.statusCritical)
  })

  it('returns muted for null pct', () => {
    expect(ctxBarColor(undefined, DEFAULT_THEME)).toBe(DEFAULT_THEME.color.muted)
  })
})

describe('ctxBarHalf', () => {
  it('returns all empty at 0%', () => {
    const { filled, empty } = ctxBarHalf(0)
    expect(filled).toBe('')
    expect(empty).toBe('░░░░')
  })

  it('shows half-block at 5% (visibility fix)', () => {
    const { filled, empty } = ctxBarHalf(5)
    expect(filled).toBe('▌')
    expect(empty).toBe('░░░')
  })

  it('shows 2 full + 2 empty at 50%', () => {
    const { filled, empty } = ctxBarHalf(50)
    expect(filled).toBe('██')
    expect(empty).toBe('░░')
  })

  it('shows 3 full + 1 empty at 75%', () => {
    const { filled, empty } = ctxBarHalf(75)
    expect(filled).toBe('███')
    expect(empty).toBe('░')
  })

  it('shows all full at 95%', () => {
    const { filled, empty } = ctxBarHalf(95)
    expect(filled).toBe('████')
    expect(empty).toBe('')
  })

  it('shows all full at 100%', () => {
    const { filled, empty } = ctxBarHalf(100)
    expect(filled).toBe('████')
    expect(empty).toBe('')
  })

  it('handles null pct as 0%', () => {
    const { filled, empty } = ctxBarHalf(undefined)
    expect(filled).toBe('')
    expect(empty).toBe('░░░░')
  })
})

// ── P3: Edge cases ────────────────────────────────────────────────────

describe('StatusRule edge cases', () => {
  it('renders without crash when usage has only total', () => {
    const element = StatusRule({ ...baseProps, usage: { total: 0 } })
    expect(textContent(element)).toContain('ready')
  })

  it('renders without crash when context_max is 0', () => {
    const element = StatusRule({
      ...baseProps,
      usage: { ...baseProps.usage, context_max: 0, context_used: 0, context_percent: 0 }
    })
    expect(textContent(element)).toContain('ready')
  })

  it('renders without crash when cwdLabel is empty', () => {
    const element = StatusRule({ ...baseProps, cwdLabel: '' })
    expect(textContent(element)).toContain('ready')
  })

  it('renders without crash when pct is null', () => {
    const element = StatusRule({
      ...baseProps,
      usage: { ...baseProps.usage, context_percent: undefined as unknown as number }
    })
    expect(textContent(element)).toContain('ready')
  })
})
