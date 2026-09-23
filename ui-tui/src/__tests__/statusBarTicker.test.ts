import { describe, expect, it } from 'vitest'

import { busyIndicatorWidth, compactCtxBar } from '../components/appChrome.js'

describe('compactCtxBar (compact context bar, 4 chars, 8-level resolution)', () => {
  it('renders all-empty at 0%', () => {
    expect(compactCtxBar(0)).toBe('░░░░')
  })

  it('shows at least one half cell from 5% occupancy up', () => {
    expect(compactCtxBar(5)).toMatch(/^▌/)
    expect(compactCtxBar(1)).toMatch(/^[█▌]/)
  })

  it('hits full at 100% and clamps beyond', () => {
    expect(compactCtxBar(100)).toBe('████')
    expect(compactCtxBar(140)).toBe('████')
  })

  it('uses half-block glyphs and halves steps between quarters', () => {
    expect(compactCtxBar(12)).toBe('▌░░░')
    expect(compactCtxBar(25)).toBe('█░░░')
    expect(compactCtxBar(37)).toBe('█▌░░')
    expect(compactCtxBar(50)).toBe('██░░')
  })

  it('always returns exactly 4 cells', () => {
    for (const pct of [0, 3, 17, 38, 50, 62, 74, 88, 97, 100]) {
      expect([...compactCtxBar(pct)].length).toBe(4)
    }
  })
})

describe('busyIndicatorWidth (no verb carousel)', () => {
  it('frame-only for verb-less styles without duration', () => {
    const w = busyIndicatorWidth('unicode', false)

    expect(w).toBeGreaterThan(0)
  })

  it('adds bounded duration width when a duration is present', () => {
    expect(busyIndicatorWidth('unicode', true)).toBeGreaterThan(busyIndicatorWidth('unicode', false))
  })
})
