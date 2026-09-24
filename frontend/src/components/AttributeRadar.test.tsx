import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { AttributeRadar, radarVertices } from './AttributeRadar'

describe('radarVertices', () => {
  it('places the first vertex straight up and all five at the given distance', () => {
    const vertices = radarVertices([10, 10, 10, 10, 10], 100)

    expect(vertices[0][0]).toBeCloseTo(0)
    expect(vertices[0][1]).toBeCloseTo(-100)
    for (const [x, y] of vertices) {
      expect(Math.hypot(x, y)).toBeCloseTo(100)
    }
  })

  it('collapses every vertex to the origin at value 0', () => {
    const vertices = radarVertices([0, 0, 0, 0, 0], 100)

    for (const [x, y] of vertices) {
      expect(x).toBeCloseTo(0)
      expect(y).toBeCloseTo(0)
    }
  })
})

describe('AttributeRadar', () => {
  it('prints each attribute value and axis label', () => {
    render(
      <AttributeRadar
        rider={{ climb: 8, sprint: 3, flat: 5, resistance: 6, positioning: 5 }}
      />,
    )

    expect(screen.getByText('8')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getAllByText('5')).toHaveLength(2)
    expect(screen.getByText('6')).toBeInTheDocument()
    expect(screen.getByText('Climb')).toBeInTheDocument()
    expect(screen.getByText('Sprint')).toBeInTheDocument()
    expect(screen.getByText('Flat')).toBeInTheDocument()
    expect(screen.getByText('Resistance')).toBeInTheDocument()
    expect(screen.getByText('Positioning')).toBeInTheDocument()
  })
})
