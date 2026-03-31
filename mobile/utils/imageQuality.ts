import { toByteArray } from "base64-js";
import jpeg from "jpeg-js";

export type NormalizedRect = {
  height: number;
  width: number;
  x: number;
  y: number;
};

export type QualityLevel = "good" | "medium" | "bad";

export type ImageQualityResult = {
  blurScore: number;
  blurVariance: number;
  edgeConfidence: number;
  edgeDensity: number;
  glareRatio: number;
  glareScore: number;
  guideBox: NormalizedRect;
  helperText: string;
  qualityLevel: QualityLevel;
  qualityScore: number;
};

const AADHAAR_ASPECT_RATIO = 1.586;
const BLUR_VARIANCE_BAD = 18;
const BLUR_VARIANCE_GOOD = 110;
const GLARE_RATIO_BAD = 0.12;
const EDGE_DENSITY_BAD = 0.04;
const EDGE_DENSITY_GOOD = 0.18;
const GOOD_QUALITY_THRESHOLD = 0.72;
const MEDIUM_QUALITY_THRESHOLD = 0.5;

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function normalize(value: number, min: number, max: number): number {
  if (max <= min) {
    return 0;
  }

  return clamp((value - min) / (max - min), 0, 1);
}

function getPixelIndex(x: number, y: number, width: number): number {
  return y * width + x;
}

export function getGuideBox(frameWidth: number, frameHeight: number): NormalizedRect {
  if (frameWidth <= 0 || frameHeight <= 0) {
    return {
      height: 0.42,
      width: 0.82,
      x: 0.09,
      y: 0.29,
    };
  }

  const targetWidth = frameWidth * 0.84;
  const targetHeight = Math.min(frameHeight * 0.52, targetWidth / AADHAAR_ASPECT_RATIO);
  const x = (frameWidth - targetWidth) / 2;
  const y = (frameHeight - targetHeight) / 2;

  return {
    height: targetHeight / frameHeight,
    width: targetWidth / frameWidth,
    x: x / frameWidth,
    y: y / frameHeight,
  };
}

function getRectBounds(rect: NormalizedRect, width: number, height: number) {
  const left = Math.max(1, Math.floor(rect.x * width));
  const top = Math.max(1, Math.floor(rect.y * height));
  const right = Math.min(width - 2, Math.floor((rect.x + rect.width) * width));
  const bottom = Math.min(height - 2, Math.floor((rect.y + rect.height) * height));

  return { bottom, left, right, top };
}

export function detectBlur(
  grayscale: Float32Array,
  width: number,
  height: number,
  rect: NormalizedRect,
): { score: number; variance: number } {
  const { bottom, left, right, top } = getRectBounds(rect, width, height);
  const values: number[] = [];

  for (let y = top; y <= bottom; y += 2) {
    for (let x = left; x <= right; x += 2) {
      const center = grayscale[getPixelIndex(x, y, width)];
      const laplacian =
        grayscale[getPixelIndex(x - 1, y, width)] +
        grayscale[getPixelIndex(x + 1, y, width)] +
        grayscale[getPixelIndex(x, y - 1, width)] +
        grayscale[getPixelIndex(x, y + 1, width)] -
        center * 4;

      values.push(laplacian);
    }
  }

  if (values.length === 0) {
    return {
      score: 0,
      variance: 0,
    };
  }

  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  const variance =
    values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / values.length;

  return {
    score: normalize(variance, BLUR_VARIANCE_BAD, BLUR_VARIANCE_GOOD),
    variance,
  };
}

export function detectGlare(
  grayscale: Float32Array,
  width: number,
  height: number,
  rect: NormalizedRect,
): { ratio: number; score: number } {
  const { bottom, left, right, top } = getRectBounds(rect, width, height);

  let sampleCount = 0;
  let overexposedCount = 0;

  for (let y = top; y <= bottom; y += 2) {
    for (let x = left; x <= right; x += 2) {
      sampleCount += 1;

      if (grayscale[getPixelIndex(x, y, width)] > 240) {
        overexposedCount += 1;
      }
    }
  }

  const ratio = sampleCount === 0 ? 1 : overexposedCount / sampleCount;

  return {
    ratio,
    score: clamp(ratio / GLARE_RATIO_BAD, 0, 1),
  };
}

export function detectCardConfidence(
  grayscale: Float32Array,
  width: number,
  height: number,
  rect: NormalizedRect,
): { confidence: number; density: number } {
  const { bottom, left, right, top } = getRectBounds(rect, width, height);

  let edgeCount = 0;
  let sampleCount = 0;

  for (let y = top; y <= bottom; y += 2) {
    for (let x = left; x <= right; x += 2) {
      const gx =
        grayscale[getPixelIndex(x + 1, y, width)] - grayscale[getPixelIndex(x - 1, y, width)];
      const gy =
        grayscale[getPixelIndex(x, y + 1, width)] - grayscale[getPixelIndex(x, y - 1, width)];

      const magnitude = Math.abs(gx) + Math.abs(gy);
      sampleCount += 1;

      if (magnitude > 45) {
        edgeCount += 1;
      }
    }
  }

  const density = sampleCount === 0 ? 0 : edgeCount / sampleCount;

  return {
    confidence: normalize(density, EDGE_DENSITY_BAD, EDGE_DENSITY_GOOD),
    density,
  };
}

export function scoreImageQuality(
  blurScore: number,
  glareScore: number,
  edgeConfidence: number,
): { helperText: string; level: QualityLevel; score: number } {
  const score = clamp(
    blurScore * 0.45 + (1 - glareScore) * 0.2 + edgeConfidence * 0.35,
    0,
    1,
  );

  if (glareScore > 0.65) {
    return {
      helperText: "Reduce glare",
      level: "bad",
      score,
    };
  }

  if (blurScore < 0.42) {
    return {
      helperText: "Hold steady",
      level: score >= MEDIUM_QUALITY_THRESHOLD ? "medium" : "bad",
      score,
    };
  }

  if (edgeConfidence < 0.45) {
    return {
      helperText: "Move closer",
      level: score >= MEDIUM_QUALITY_THRESHOLD ? "medium" : "bad",
      score,
    };
  }

  if (score >= GOOD_QUALITY_THRESHOLD) {
    return {
      helperText: "Looks good",
      level: "good",
      score,
    };
  }

  if (score >= MEDIUM_QUALITY_THRESHOLD) {
    return {
      helperText: "Adjust framing",
      level: "medium",
      score,
    };
  }

  return {
    helperText: "Move closer",
    level: "bad",
    score,
  };
}

function decodeBase64Image(base64: string) {
  const bytes = toByteArray(base64);
  return jpeg.decode(bytes, {
    formatAsRGBA: true,
    tolerantDecoding: true,
    useTArray: true,
  });
}

function rgbaToGrayscale(data: Uint8Array, width: number, height: number): Float32Array {
  const grayscale = new Float32Array(width * height);

  for (let index = 0; index < width * height; index += 1) {
    const base = index * 4;
    const red = data[base] ?? 0;
    const green = data[base + 1] ?? 0;
    const blue = data[base + 2] ?? 0;

    grayscale[index] = red * 0.299 + green * 0.587 + blue * 0.114;
  }

  return grayscale;
}

export function getEmptyQualityResult(): ImageQualityResult {
  return {
    blurScore: 0,
    blurVariance: 0,
    edgeConfidence: 0,
    edgeDensity: 0,
    glareRatio: 1,
    glareScore: 1,
    guideBox: getGuideBox(0, 0),
    helperText: "Center the Aadhaar card",
    qualityLevel: "bad",
    qualityScore: 0,
  };
}

export function analyzePreviewImage(
  base64: string | null | undefined,
): ImageQualityResult {
  if (!base64) {
    return getEmptyQualityResult();
  }

  try {
    const decoded = decodeBase64Image(base64);
    const guideBox = getGuideBox(decoded.width, decoded.height);
    const grayscale = rgbaToGrayscale(decoded.data, decoded.width, decoded.height);
    const blur = detectBlur(grayscale, decoded.width, decoded.height, guideBox);
    const glare = detectGlare(grayscale, decoded.width, decoded.height, guideBox);
    const card = detectCardConfidence(grayscale, decoded.width, decoded.height, guideBox);
    const quality = scoreImageQuality(blur.score, glare.score, card.confidence);

    return {
      blurScore: blur.score,
      blurVariance: blur.variance,
      edgeConfidence: card.confidence,
      edgeDensity: card.density,
      glareRatio: glare.ratio,
      glareScore: glare.score,
      guideBox,
      helperText: quality.helperText,
      qualityLevel: quality.level,
      qualityScore: quality.score,
    };
  } catch {
    return {
      ...getEmptyQualityResult(),
      helperText: "Move closer",
    };
  }
}

