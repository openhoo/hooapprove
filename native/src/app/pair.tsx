import { useLocalSearchParams } from 'expo-router';
import Pairing from '../screens/Pairing';
export default function PairRoute() {
  const { token } = useLocalSearchParams<{ token?: string }>();
  // Deep links prefill only; preview and enrollment require explicit user actions.
  return <Pairing initialCode={typeof token === 'string' ? token : ''} />;
}
