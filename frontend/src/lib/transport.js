import { Car, Plane, TrainFront, Footprints, HelpCircle } from "lucide-react";

export const TRANSPORT_MODES = [
  { value: "car", label: "Car", Icon: Car },
  { value: "plane", label: "Plane", Icon: Plane },
  { value: "train", label: "Train", Icon: TrainFront },
  { value: "walk", label: "Walk", Icon: Footprints },
  { value: "other", label: "Other", Icon: HelpCircle },
];

export function transportOf(value) {
  return TRANSPORT_MODES.find((m) => m.value === value) || TRANSPORT_MODES[0];
}
