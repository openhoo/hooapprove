import { Redirect } from 'expo-router';
// The authentication promise receives the ticket; navigation never displays or stores it.
export default function Callback() { return <Redirect href="/" />; }
