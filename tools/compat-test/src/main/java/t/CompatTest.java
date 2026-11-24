package t;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.bukkit.Bukkit;
import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.World;
import org.bukkit.entity.Entity;
import org.bukkit.entity.EntityType;
import org.bukkit.entity.Zombie;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.entity.EntityDamageEvent;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.scheduler.BukkitRunnable;

public final class CompatTest extends JavaPlugin implements Listener {
    private final List<UUID> zombies = new ArrayList<>();
    private Zombie a, b;
    private int ok, fail;

    private void check(String name, Runnable r) {
        try { r.run(); ok++; getLogger().info("PASS " + name); }
        catch (Throwable t) { fail++; getLogger().warning("FAIL " + name + ": " + t); }
    }

    @Override
    public void onEnable() {
        getServer().getPluginManager().registerEvents(this, this);
        check("scoreboard new + team + objective", () -> { var sb = Bukkit.getScoreboardManager().getNewScoreboard(); sb.registerNewTeam("t1"); sb.registerNewObjective("o1", org.bukkit.scoreboard.Criteria.DUMMY, net.kyori.adventure.text.Component.text("o")); });
        check("main scoreboard team", () -> Bukkit.getScoreboardManager().getMainScoreboard().registerNewTeam("maint"));
        check("onEnable read block in unloaded chunk", () -> getLogger().info("type=" + Bukkit.getWorlds().get(0).getBlockAt(5000, 64, 5000).getType()));
        check("onEnable region scheduler at unloaded chunk", () -> Bukkit.getRegionScheduler().runAtFixedRate(this, new Location(Bukkit.getWorlds().get(0), 8000, 64, 8000), t -> { getLogger().info("regiontask ok"); t.cancel(); }, 1, 20));
        check("createWorld on enable", () -> { World nw = new org.bukkit.WorldCreator("compat_world").createWorld(); if (nw == null) throw new IllegalStateException("null world"); });
        World w = Bukkit.getWorlds().get(0);
        new BukkitRunnable() {
            int tick = 0;
            @Override public void run() {
                tick++;
                if (tick == 2) {
                    check("global getCurrentTick", () -> getLogger().info("currentTick=" + Bukkit.getCurrentTick()));
                    check("global read unloaded far block", () -> getLogger().info("far=" + w.getBlockAt(-3000, 64, 3000).getType()));
                    check("global far block getBiome", () -> getLogger().info("biome=" + w.getBlockAt(-3000, 64, 3000).getBiome()));
                }
                if (tick == 1) {
                    check("forceload chunks", () -> { w.setChunkForceLoaded(0, 0, true); w.setChunkForceLoaded(125, 0, true); });
                } else if (tick == 60) {
                    check("spawn A", () -> { a = (Zombie) w.spawnEntity(new Location(w, 8, w.getHighestBlockYAt(8, 8) + 1, 8), EntityType.ZOMBIE); a.setAI(false); a.setPersistent(true); });
                    check("spawn B", () -> { b = (Zombie) w.spawnEntity(new Location(w, 2008, w.getHighestBlockYAt(2008, 8) + 1, 8), EntityType.ZOMBIE); b.setAI(false); b.setPersistent(true); });
                    check("name A", () -> a.setCustomName("A"));
                    check("name B", () -> b.setCustomName("B"));
                    check("block far setType", () -> w.getBlockAt(2000, 100, 0).setType(Material.GOLD_BLOCK));
                    check("block far read", () -> { if (w.getBlockAt(2000, 100, 0).getType() != Material.GOLD_BLOCK) throw new IllegalStateException("not set"); });
                    check("chest far place", () -> w.getBlockAt(2001, 100, 0).setType(Material.CHEST));
                    check("chest far add item", () -> ((org.bukkit.block.Chest) w.getBlockAt(2001, 100, 0).getState()).getInventory().addItem(new org.bukkit.inventory.ItemStack(Material.DIAMOND, 3)));
                    check("chest far read item", () -> { int n = ((org.bukkit.block.Chest) w.getBlockAt(2001, 100, 0).getState()).getInventory().all(Material.DIAMOND).values().stream().mapToInt(org.bukkit.inventory.ItemStack::getAmount).sum(); if (n != 3) throw new IllegalStateException("diamonds=" + n); });
                    check("teleport A same region", () -> a.teleport(new Location(w, 10, a.getLocation().getY(), 10)));
                    check("damage B (event touches A)", () -> b.damage(1.0));
                } else if (tick == 120) {
                    check("teleport A to B region", () -> a.teleport(b.getLocation().add(2, 0, 0)));
                } else if (tick == 200) {
                    check("A arrived near B", () -> { if (Math.abs(a.getLocation().getX() - 2010) > 1) throw new IllegalStateException("A at " + a.getLocation()); });
                    check("count entities", () -> getLogger().info("entities=" + w.getEntities().size() + " zombies=" + w.getEntitiesByClass(Zombie.class).size()));
                    check("nearby B", () -> getLogger().info("nearB=" + b.getNearbyEntities(5, 5, 5).size()));
                    check("remove", () -> { a.remove(); b.remove(); });
                    check("world list", () -> getLogger().info("worlds=" + Bukkit.getWorlds().stream().map(World::getName).toList()));
                    check("spawn in created world", () -> { World nw = Bukkit.getWorld("compat_world"); nw.setChunkForceLoaded(0, 0, true); });
                    getLogger().info("RESULT ok=" + ok + " fail=" + fail);
                    cancel();
                }
            }
        }.runTaskTimer(this, 1L, 1L);
    }

    @Override
    public void onDisable() {
        for (World dw : Bukkit.getWorlds()) {
            for (Entity e : dw.getEntities()) {
                if (e instanceof org.bukkit.entity.Mob m) {
                    check("onDisable mob setAware", () -> m.setAware(true));
                }
            }
        }
        getLogger().info("DISABLE ok=" + ok + " fail=" + fail);
    }

    @EventHandler
    public void onDamage(EntityDamageEvent e) {
        if (e.getEntity() == b && a != null) {
            check("in event: rename A from B's region", () -> a.setCustomName("A-touched"));
            check("in event: read A health", () -> getLogger().info("A health=" + a.getHealth()));
        }
    }
}
