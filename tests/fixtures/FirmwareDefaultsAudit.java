package golf.thinkbluefix;

import de.vw.mib.asl.framework.api.diagnosis.config.EcoHmi;
import de.vw.mib.asl.framework.internal.diagnosis.variant.std2.EcoHmiImpl;
import de.vw.mib.asl.framework.internal.framework.ServiceManager;
import de.vw.mib.log4mib.Logger;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Arrays;

/** Offline fixture compiled against the local stock HMI reference. */
public final class FirmwareDefaultsAudit {
    private static final int FIRST_OVERRIDE = 747;
    private static final int LAST_OVERRIDE = 838;
    private static final int[][] STOCK_PROFILES = {
        {1, 1}, {1, 2}, {1, 3}, {3, 1}, {3, 2}, {3, 3}, {4, 4}
    };

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void installFixtureLogger() {
        Class<Logger> logger = Logger.class;
        ServiceManager.logger = (Logger) Proxy.newProxyInstance(
                logger.getClassLoader(), new Class<?>[] {logger}, new InvocationHandler() {
                    public Object invoke(Object proxy, Method method, Object[] arguments) {
                        Class<?> type = method.getReturnType();
                        if (type.isInstance(proxy)) {
                            return proxy;
                        }
                        if (type.isInterface()) {
                            return Proxy.newProxyInstance(type.getClassLoader(), new Class<?>[] {type}, this);
                        }
                        return null;
                    }
                });
    }

    public static void main(String[] expectedProfiles) {
        installFixtureLogger();
        EcoHmi blank = new EcoHmiImpl(new byte[102]);
        byte[] customBytes = new byte[102];
        customBytes[0] = 1;
        EcoHmi custom = new EcoHmiImpl(customBytes);
        byte[] reservedBytes = new byte[102];
        reservedBytes[101] = 1;
        EcoHmi reserved = new EcoHmiImpl(reservedBytes);
        EcoHmi malformed = new EcoHmiImpl(new byte[101]);
        EcoHmi alternate = new de.vw.mib.asl.framework.internal.diagnosis.variant.high2.EcoHmiImpl(new byte[102]);

        int matches = 0;
        for (int[] profile : STOCK_PROFILES) {
            int engine = profile[0];
            int gear = profile[1];
            String pair = engine + "," + gear;
            boolean expected = Arrays.asList(expectedProfiles).contains(pair);
            EcoHmi result = FirmwareDefaults.preserve(blank, engine, gear);
            check((result != blank) == expected, "Selection mismatch for " + pair);
            check(FirmwareDefaults.preserve(custom, engine, gear) == custom, "Populated field changed");
            check(FirmwareDefaults.preserve(reserved, engine, gear) == reserved, "Reserved byte ignored");
            check(FirmwareDefaults.preserve(malformed, engine, gear) == malformed, "Short buffer masked");
            check(FirmwareDefaults.preserve(alternate, engine, gear) == alternate, "Other implementation masked");
            check(FirmwareDefaults.preserve(null, engine, gear) == null, "Null response replaced");
            if (!expected) {
                continue;
            }

            matches++;
            check(result.getRawData() == blank.getRawData(), "Raw buffer identity changed");
            check(Arrays.equals(result.getRawData(), new byte[102]), "Raw buffer contents changed");
            check(FirmwareDefaults.preserve(result, engine, gear) == result, "Mask applied twice");
            for (int id = FIRST_OVERRIDE; id <= LAST_OVERRIDE; id++) {
                check(blank.contains(id), "Stock descriptor is missing " + id);
                check(!result.contains(id), "Override remains present " + id);
                check(result.getValue(id) == blank.getValue(id), "Native value changed " + id);
            }
            check(result.contains(FIRST_OVERRIDE - 1) == blank.contains(FIRST_OVERRIDE - 1), "Lower boundary changed");
            check(result.contains(LAST_OVERRIDE + 1) == blank.contains(LAST_OVERRIDE + 1), "Upper boundary changed");
        }

        check(matches == expectedProfiles.length, "Unexpected or duplicate expected profile");
        int[][] unknownProfiles = {{0, 0}, {1, 4}, {3, 4}, {4, 1}, {-1, -1}, {99, 99}};
        for (int[] profile : unknownProfiles) {
            check(FirmwareDefaults.preserve(blank, profile[0], profile[1]) == blank, "Unknown profile matched");
        }
        System.out.println("Verified blank EcoHmi masking for " + matches + " selected native profiles");
    }
}
