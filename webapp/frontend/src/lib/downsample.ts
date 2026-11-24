/**
 * Largest-Triangle-Three-Buckets (LTTB) downsampling for large time-series plots.
 * Preserves visual shape, peaks, and endpoints when rendering > threshold points.
 */
export function downsampleLttb<T>(
  points: readonly T[],
  threshold: number,
  getX: (point: T, index: number) => number,
  getY: (point: T) => number,
): T[] {
  const n = points.length;
  if (n <= threshold || threshold < 3) {
    return points.slice();
  }

  const sampled: T[] = [points[0]];
  const bucketSize = (n - 2) / (threshold - 2);
  let a = 0;

  for (let i = 0; i < threshold - 2; i += 1) {
    const avgRangeStart = Math.floor((i + 1) * bucketSize) + 1;
    const avgRangeEnd = Math.min(Math.floor((i + 2) * bucketSize) + 1, n);
    let avgX = 0;
    let avgY = 0;
    const avgRangeLength = Math.max(1, avgRangeEnd - avgRangeStart);
    for (let j = avgRangeStart; j < avgRangeEnd; j += 1) {
      avgX += getX(points[j], j);
      avgY += getY(points[j]);
    }
    avgX /= avgRangeLength;
    avgY /= avgRangeLength;

    const rangeOffs = Math.floor(i * bucketSize) + 1;
    const rangeTo = Math.min(Math.floor((i + 1) * bucketSize) + 1, n - 1);
    const pointAX = getX(points[a], a);
    const pointAY = getY(points[a]);

    let maxArea = -1;
    let nextA = rangeOffs;
    for (let j = rangeOffs; j < rangeTo; j += 1) {
      const area = Math.abs(
        (pointAX - avgX) * (getY(points[j]) - pointAY) -
          (pointAX - getX(points[j], j)) * (avgY - pointAY),
      );
      if (area > maxArea) {
        maxArea = area;
        nextA = j;
      }
    }

    sampled.push(points[nextA]);
    a = nextA;
  }

  sampled.push(points[n - 1]);
  return sampled;
}
