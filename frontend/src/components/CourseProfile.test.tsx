import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { CourseProfile } from './CourseProfile'

/** The drawn course, as one pair of y coordinates per segment stroke
 * (y of the segment's start and end). y grows downward in SVG, so a
 * climb makes the second y smaller. */
function segmentYs(container: HTMLElement): number[][] {
  const strokes = container.querySelectorAll('path[fill="none"]')
  return Array.from(strokes).map((stroke) => {
    const nums = stroke
      .getAttribute('d')!
      .match(/-?\d+(?:\.\d+)?/g)!
      .map(Number)
    return [nums[1], nums[3]]
  })
}

describe('CourseProfile', () => {
  it('renders the shared elevation chart for a climbing course', () => {
    const course = [
      { length: 40000, gradient: 4 },
      { length: 60000, gradient: 2 },
    ]
    const { container } = render(<CourseProfile course={course} />)

    expect(container.querySelector('svg[aria-label="Elevation profile"]')).not.toBeNull()
    // rising elevation: the first segment's endpoints sit at different heights
    const [first] = segmentYs(container)
    expect(first[0]).not.toBe(first[1])
    expect(screen.getByText('4%')).toBeInTheDocument()
    expect(screen.getByText('elevation (m)')).toBeInTheDocument()
    expect(screen.getByText('distance (km)')).toBeInTheDocument()
  })

  it('renders a flat course as a level line', () => {
    const course = [{ length: 110000, gradient: 0 }]
    const { container } = render(<CourseProfile course={course} />)

    expect(container.querySelector('svg[aria-label="Elevation profile"]')).not.toBeNull()
    const [first] = segmentYs(container)
    expect(first[0]).toBe(first[1])
    expect(screen.getByText('0%')).toBeInTheDocument()
  })
})