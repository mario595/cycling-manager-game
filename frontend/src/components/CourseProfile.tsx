import CourseChart from '../../../race_player/src/components/CourseChart'
import { computeProfile } from '../../../race_player/src/utils/profile'
import type { Segment } from '../../../race_player/src/types/race'

/** The course as the shared elevation chart — the same derivation and drawing
 * code as the race_player visualizer, imported directly from its source so
 * the calendar and the visualizer can never drift apart. No rider markers
 * here; the race has not necessarily run, and the chart stands alone. */
export function CourseProfile({ course }: { course: Segment[] }) {
  return <CourseChart profile={computeProfile(course)} height={200} />
}