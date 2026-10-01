import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { RaceMarker } from '../api'
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

  it('draws a line and a list entry per marker', () => {
    const course = [{ length: 110000, gradient: 0 }]
    const markers: RaceMarker[] = [
      { id: 1, kind: 'sprint', name: 'Line One', distance: 40000, weight: 'standard', category: null, points: [6, 4, 3, 2, 1] },
      { id: 2, kind: 'mountain', name: 'Summit', distance: 80000, weight: null, category: 'cat2', points: [6, 4, 3, 2, 1] },
    ]
    const { container } = render(<CourseProfile course={course} markers={markers} />)

    expect(container.querySelectorAll('line[stroke-dasharray]')).toHaveLength(2)
    expect(screen.getByText(/Sprint · Line One · km 40\.0/)).toBeInTheDocument()
    expect(screen.getByText(/Mountain · Summit · km 80\.0/)).toBeInTheDocument()
  })

  it('renders nothing extra without markers', () => {
    const { container } = render(<CourseProfile course={[{ length: 110000, gradient: 0 }]} />)

    expect(container.querySelectorAll('line[stroke-dasharray]')).toHaveLength(0)
    expect(screen.queryByText(/Sprint|Mountain/)).toBeNull()
  })

  it('shows weight and winner points for a sprint marker', () => {
    const course = [{ length: 110000, gradient: 0 }]
    const markers: RaceMarker[] = [
      { id: 1, kind: 'sprint', name: 'Big One', distance: 40000, weight: 'major', category: null, points: [10, 7, 5, 3, 2] },
    ]
    render(<CourseProfile course={course} markers={markers} />)

    expect(screen.getByText(/Major/)).toBeInTheDocument()
    expect(screen.getByText(/10 pts to the winner/)).toBeInTheDocument()
  })

  it('mountain marker shows no weight', () => {
    const course = [{ length: 110000, gradient: 0 }]
    const markers: RaceMarker[] = [
      { id: 1, kind: 'mountain', name: 'Summit', distance: 40000, weight: null, category: 'cat2', points: [6, 4, 3, 2, 1] },
    ]
    render(<CourseProfile course={course} markers={markers} />)

    expect(screen.queryByText(/Minor|Standard|Major/)).toBeNull()
  })

  it('shows category and winner points for a mountain marker', () => {
    const course = [{ length: 110000, gradient: 0 }]
    const markers: RaceMarker[] = [
      { id: 1, kind: 'mountain', name: 'Final Top', distance: 110000, weight: null, category: 'hc', points: [10, 7, 5, 3, 2] },
    ]
    render(<CourseProfile course={course} markers={markers} />)

    expect(screen.getByText(/HC/)).toBeInTheDocument()
    expect(screen.getByText(/10 pts to the winner/)).toBeInTheDocument()
  })
})