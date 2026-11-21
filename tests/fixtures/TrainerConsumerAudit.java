package golf.thinkbluefix;

import de.vw.mib.asl.ASLPropertyManager;
import de.vw.mib.asl.api.car.thinkblue.TBTServiceListener;
import de.vw.mib.asl.api.car.thinkblue.TBTServiceListenerAdapter;
import de.vw.mib.asl.framework.api.diagnosis.config.EcoHmi;
import de.vw.mib.asl.framework.internal.diagnosis.variant.std2.EcoHmiImpl;
import de.vw.mib.asl.framework.internal.framework.ServiceManager;
import de.vw.mib.asl.internal.car.framework.services.ServiceFactory;
import de.vw.mib.asl.internal.car.thinkblue.ASLTargetThinkBlue;
import de.vw.mib.asl.internal.car.thinkblue.calc.BlueCalculator;
import de.vw.mib.asl.internal.car.thinkblue.calc.BlueManager;
import de.vw.mib.asl.internal.car.thinkblue.calc.table.DrivingState;
import de.vw.mib.asl.internal.car.thinkblue.calc.table.DrivingTable;
import de.vw.mib.collections.ints.IntIntOptHashMap;
import de.vw.mib.log4mib.Logger;
import java.io.File;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/** Compare the real consumer before and after reading a blank block on a desktop JVM. */
public final class TrainerConsumerAudit {
    private static final Class<?> TRAINER = ASLTargetThinkBlue.class;

    private static Field field(Class<?> owner, String name) throws Exception {
        for (Class<?> type = owner; type != null; type = type.getSuperclass()) {
            try {
                Field field = type.getDeclaredField(name);
                field.setAccessible(true);
                return field;
            } catch (NoSuchFieldException ignored) { }
        }
        throw new NoSuchFieldException(name);
    }

    private static Method method(String name, Class<?>... parameters) throws Exception {
        Method method = TRAINER.getDeclaredMethod(name, parameters);
        method.setAccessible(true);
        return method;
    }

    private static <T> T service(Class<T> type) {
        return type.cast(Proxy.newProxyInstance(type.getClassLoader(), new Class<?>[] {type}, (p, m, a) -> {
            Class<?> result = m.getReturnType();
            if (result == Boolean.TYPE) return false;
            if (result == Integer.TYPE) return 0;
            if (result.isInterface()) return service(result);
            return null;
        }));
    }

    private static ASLTargetThinkBlue target(int engine, int gear) throws Exception {
        Class<?> unsafe = Class.forName("sun.misc.Unsafe");
        Object allocator = field(unsafe, "theUnsafe").get(null);
        // Skip the event-bus constructor. Only the stock configuration consumer is exercised.
        ASLTargetThinkBlue target = (ASLTargetThinkBlue) unsafe.getMethod("allocateInstance", Class.class)
                .invoke(allocator, TRAINER);
        field(TRAINER, "logger").set(target, ServiceManager.logger);
        field(TRAINER, "engineType").setInt(target, engine);
        field(TRAINER, "gearType").setInt(target, gear);
        field(TRAINER, "isCombustionOnly").setBoolean(target, engine == 1);
        field(TRAINER, "isElectricOnly").setBoolean(target, engine == 4);
        field(TRAINER, "isHybrid").setBoolean(null, engine == 3);
        field(TRAINER, "histMaxValues").set(target, new IntIntOptHashMap());
        field(TRAINER, "tables").set(target, new DrivingTable[4]);
        method("changeDrivingTable").invoke(target);
        String historyType = engine == 4 ? "Electric" : engine == 3 ? "Hybrid" : "Combustion";
        method("initHistoryMaxValues" + historyType).invoke(target);
        field(TRAINER, "calculator").set(target, new BlueCalculator());
        field(TRAINER, "blueManager").set(target, new BlueManager(target));
        return target;
    }

    private static List<Integer> snapshot(ASLTargetThinkBlue target) throws Exception {
        List<Integer> values = new ArrayList<>();
        Object calculator = field(TRAINER, "calculator").get(target);
        Object manager = field(TRAINER, "blueManager").get(target);
        values.add(field(BlueCalculator.class, "hintDuration").getInt(calculator));
        values.add(field(BlueCalculator.class, "maxAcceleration").getInt(calculator));
        values.add(field(BlueManager.class, "timeTrend").getInt(manager));
        IntIntOptHashMap history = (IntIntOptHashMap) field(TRAINER, "histMaxValues").get(target);
        for (int unit = 0; unit < 32; unit++) values.add(history.get(unit));
        for (DrivingTable table : (DrivingTable[]) field(TRAINER, "tables").get(target)) {
            if (table == null) continue;
            for (DrivingState state : (DrivingState[]) field(table.getClass(), "drivingStates").get(table)) {
                if (state == null) continue;
                values.add(state.getW1());
                values.add(state.getW2());
                values.add(state.getRating());
            }
        }
        return values;
    }

    public static void main(String[] args) throws Exception {
        File loadedFrom = new File(TRAINER.getProtectionDomain().getCodeSource().getLocation().toURI());
        if (!loadedFrom.getCanonicalFile().equals(new File(args[0]).getCanonicalFile())) {
            throw new AssertionError("Expected Trainer class was not loaded");
        }
        ServiceManager.logger = service(Logger.class);
        ServiceManager.aslPropertyManager = service(ASLPropertyManager.class);
        field(TRAINER, "logMsg").set(null, ServiceManager.logger);
        ServiceFactory.getInstance().getServiceClientRegistry()
                .registerServiceClient(TBTServiceListener.class, new TBTServiceListenerAdapter());

        Method consume = method("readDiagnosisData", EcoHmi.class);
        List<String> selected = Arrays.asList(args).subList(1, args.length);
        int[][] profiles = {{1, 1}, {1, 2}, {1, 3}, {3, 1}, {3, 2}, {3, 3}, {4, 4}};
        for (int[] profile : profiles) {
            String pair = profile[0] + "," + profile[1];
            ASLTargetThinkBlue target = target(profile[0], profile[1]);
            List<Integer> defaults = snapshot(target);
            consume.invoke(target, new EcoHmiImpl(new byte[102]));
            if (defaults.equals(snapshot(target)) != selected.contains(pair)) {
                throw new AssertionError("Unexpected native result for " + pair);
            }
        }
        System.out.println("Verified real Trainer consumer for all seven native classifications");
    }
}
