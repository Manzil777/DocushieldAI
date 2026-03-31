declare module "jpeg-js" {
  export type DecodedImage = {
    data: Uint8Array;
    height: number;
    width: number;
  };

  export function decode(
    data: Uint8Array,
    options?: {
      formatAsRGBA?: boolean;
      tolerantDecoding?: boolean;
      useTArray?: boolean;
    },
  ): DecodedImage;

  const jpeg: {
    decode: typeof decode;
  };

  export default jpeg;
}
