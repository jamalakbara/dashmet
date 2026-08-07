import { describe, expect, it } from "vitest";

import { metricDelta } from "./formatters";

describe("metricDelta", () => {
  describe("non-cost metrics (increase is good)", () => {
    it.each(["spend", "roas", "conversions"])(
      "%s: increase → direction up with signed label",
      (key) => {
        // (112.5 - 100) / 100 * 100 = 12.5
        expect(metricDelta(112.5, 100, key)).toEqual({
          label: "+12.5%",
          direction: "up",
        });
      },
    );

    it.each(["spend", "roas", "conversions"])(
      "%s: decrease → direction down with negative label",
      (key) => {
        // (92 - 100) / 100 * 100 = -8.0
        expect(metricDelta(92, 100, key)).toEqual({
          label: "-8.0%",
          direction: "down",
        });
      },
    );
  });

  describe("cost metrics (decrease is good — inverted)", () => {
    it.each(["cpa", "cpc", "cpm", "cpp", "frequency"])(
      "%s: decrease → direction up (good)",
      (key) => {
        expect(metricDelta(92, 100, key)).toEqual({
          label: "-8.0%",
          direction: "up",
        });
      },
    );

    it.each(["cpa", "cpc", "cpm", "cpp", "frequency"])(
      "%s: increase → direction down (bad)",
      (key) => {
        expect(metricDelta(112.5, 100, key)).toEqual({
          label: "+12.5%",
          direction: "down",
        });
      },
    );
  });

  describe("cost_per_ prefix is treated as a cost metric (inverted)", () => {
    it("cost_per_result: decrease → up (good)", () => {
      expect(metricDelta(92, 100, "cost_per_result")).toEqual({
        label: "-8.0%",
        direction: "up",
      });
    });

    it("cost_per_result: increase → down (bad)", () => {
      expect(metricDelta(112.5, 100, "cost_per_result")).toEqual({
        label: "+12.5%",
        direction: "down",
      });
    });
  });

  describe("neutral guard (no usable comparison)", () => {
    it("null current → neutral", () => {
      expect(metricDelta(null, 100, "spend")).toEqual({
        label: "—",
        direction: "neutral",
      });
    });

    it("null previous → neutral", () => {
      expect(metricDelta(100, null, "spend")).toEqual({
        label: "—",
        direction: "neutral",
      });
    });

    it("undefined current/previous → neutral (== null catches undefined)", () => {
      expect(metricDelta(undefined, 100, "spend")).toEqual({
        label: "—",
        direction: "neutral",
      });
      expect(metricDelta(100, undefined, "spend")).toEqual({
        label: "—",
        direction: "neutral",
      });
    });

    it("previous === 0 (would divide by zero) → neutral", () => {
      expect(metricDelta(100, 0, "spend")).toEqual({
        label: "—",
        direction: "neutral",
      });
    });
  });

  describe("zero change", () => {
    it("current === previous → label 0.0%, direction neutral", () => {
      expect(metricDelta(100, 100, "spend")).toEqual({
        label: "0.0%",
        direction: "neutral",
      });
    });

    it("zero change is neutral even for a cost metric", () => {
      expect(metricDelta(100, 100, "cpa")).toEqual({
        label: "0.0%",
        direction: "neutral",
      });
    });
  });
});
