export const STAGE_WIDTH = 800;
export const STAGE_HEIGHT = 600;
export const AREA_WIDTH = STAGE_WIDTH / 2;
export const AREA_HEIGHT = STAGE_HEIGHT / 2;

export const AREA_OFFSETS: Record<string, { x: number; y: number }> = {
  Bedroom: { x: 0, y: 0 },
  Office: { x: AREA_WIDTH, y: 0 },
  Bathroom: { x: 0, y: AREA_HEIGHT },
  Lounge: { x: AREA_WIDTH, y: AREA_HEIGHT },
};

export const NPCDotSize = 12;
export const EmojiSize = 20;
export const NameFontSize = 10;
export const ANIMATION_DURATION_SECONDS = 0.8;
export const IDLE_MOVEMENT_RANGE = 3;
export const IDLE_MOVEMENT_INTERVAL_MS = 3000;
export const MARGIN = 50;
