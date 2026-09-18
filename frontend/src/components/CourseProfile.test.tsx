import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { CourseProfile } from './CourseProfile'

function yValues(path: string): number[] {
  return path.split(' ').map((pair) => Number(pair.split(',')[1]))
}

describe('CourseProfile', () => {
  it('renders a polyline with varying y for a climbing course', () => {
    const course = [{ length: 10000, gradient: 0.05 }]
    const { container } = render(<CourseProfile course={course} />)

    const polyline = container.querySelector('polyline')
    expect(polyline).not.toBeNull()
    const ys = yValues(polyline!.getAttribute('points')!)
    expect(new Set(ys).size).toBeGreaterThan(1)
  })

  it('renders without throwing for a flat course', () => {
    const course = [
      { length: 10000, gradient: 0 },
      { length: 20000, gradient: 0 },
    ]
    const { container } = render(<CourseProfile course={course} />)

    expect(container.querySelector('polyline')).not.toBeNull()
  })
})