ALTER TABLE product ADD COLUMN calories_per_100 REAL CHECK(calories_per_100 IS NULL OR (calories_per_100>=0 AND calories_per_100<=2000));
ALTER TABLE product ADD COLUMN calorie_basis TEXT NOT NULL DEFAULT 'per_100g' CHECK(calorie_basis IN ('per_100g','per_100ml'));
ALTER TABLE product ADD COLUMN calorie_status TEXT NOT NULL DEFAULT 'estimated' CHECK(calorie_status IN ('estimated','label_verified'));
ALTER TABLE product ADD COLUMN calorie_source TEXT;
ALTER TABLE product ADD COLUMN calorie_notes TEXT;
DROP TRIGGER product_search_insert;
DROP TRIGGER product_search_update;
DROP TRIGGER product_search_delete;
DROP TRIGGER category_search_update;
DROP TABLE product_fts;
CREATE VIRTUAL TABLE product_fts USING fts5(name,category,description,nutrition,tokenize='unicode61');
INSERT INTO product_fts(rowid,name,category,description,nutrition) SELECT p.product_id,p.name,c.name,p.description,CASE WHEN p.calories_per_100 IS NULL THEN '' ELSE 'Calories: ' || p.calories_per_100 || ' kcal ' || replace(p.calorie_basis,'_',' ') || '. ' || p.calorie_status || '. ' || coalesce(p.calorie_notes,'') END FROM product p JOIN category c USING(category_id);
CREATE TRIGGER product_search_insert AFTER INSERT ON product BEGIN
 INSERT INTO product_fts(rowid,name,category,description,nutrition)
 VALUES(NEW.product_id,NEW.name,(SELECT name FROM category WHERE category_id=NEW.category_id),NEW.description,CASE WHEN NEW.calories_per_100 IS NULL THEN '' ELSE 'Calories: ' || NEW.calories_per_100 || ' kcal ' || replace(NEW.calorie_basis,'_',' ') || '. ' || NEW.calorie_status || '. ' || coalesce(NEW.calorie_notes,'') END);
 INSERT INTO product_index_jobs(product_id,revision) VALUES(NEW.product_id,NEW.search_revision)
 ON CONFLICT(product_id) DO UPDATE SET revision=excluded.revision,operation='upsert',status='pending',attempts=0,error=NULL,next_attempt_at=0,updated_at=datetime('now');
END;

CREATE TRIGGER product_search_update AFTER UPDATE OF name,description,category_id,price,stock_quantity,image_path,calories_per_100,calorie_basis,calorie_status,calorie_source,calorie_notes ON product
WHEN OLD.name IS NOT NEW.name OR OLD.description IS NOT NEW.description OR OLD.category_id IS NOT NEW.category_id
 OR OLD.price IS NOT NEW.price OR OLD.stock_quantity IS NOT NEW.stock_quantity OR OLD.image_path IS NOT NEW.image_path
 OR OLD.calories_per_100 IS NOT NEW.calories_per_100 OR OLD.calorie_basis IS NOT NEW.calorie_basis
 OR OLD.calorie_status IS NOT NEW.calorie_status OR OLD.calorie_source IS NOT NEW.calorie_source OR OLD.calorie_notes IS NOT NEW.calorie_notes
BEGIN
 UPDATE product SET search_revision=OLD.search_revision+1 WHERE product_id=NEW.product_id;
 DELETE FROM product_fts WHERE rowid=NEW.product_id;
 INSERT INTO product_fts(rowid,name,category,description,nutrition)
 VALUES(NEW.product_id,NEW.name,(SELECT name FROM category WHERE category_id=NEW.category_id),NEW.description,CASE WHEN NEW.calories_per_100 IS NULL THEN '' ELSE 'Calories: ' || NEW.calories_per_100 || ' kcal ' || replace(NEW.calorie_basis,'_',' ') || '. ' || NEW.calorie_status || '. ' || coalesce(NEW.calorie_notes,'') END);
 INSERT INTO product_index_jobs(product_id,revision) VALUES(NEW.product_id,OLD.search_revision+1)
 ON CONFLICT(product_id) DO UPDATE SET revision=excluded.revision,operation='upsert',status='pending',attempts=0,error=NULL,next_attempt_at=0,updated_at=datetime('now');
END;

CREATE TRIGGER product_search_delete AFTER DELETE ON product BEGIN
 DELETE FROM product_fts WHERE rowid=OLD.product_id;
 INSERT INTO product_index_jobs(product_id,revision,operation) VALUES(OLD.product_id,OLD.search_revision+1,'delete')
 ON CONFLICT(product_id) DO UPDATE SET revision=excluded.revision,operation='delete',status='pending',attempts=0,error=NULL,next_attempt_at=0,updated_at=datetime('now');
END;

CREATE TRIGGER category_search_update AFTER UPDATE OF name ON category WHEN OLD.name IS NOT NEW.name BEGIN
 UPDATE product SET search_revision=search_revision+1 WHERE category_id=NEW.category_id;
 DELETE FROM product_fts WHERE rowid IN (SELECT product_id FROM product WHERE category_id=NEW.category_id);
 INSERT INTO product_fts(rowid,name,category,description,nutrition)
 SELECT p.product_id,p.name,NEW.name,p.description,CASE WHEN p.calories_per_100 IS NULL THEN '' ELSE 'Calories: ' || p.calories_per_100 || ' kcal ' || replace(p.calorie_basis,'_',' ') || '. ' || p.calorie_status || '. ' || coalesce(p.calorie_notes,'') END FROM product p WHERE category_id=NEW.category_id;
 INSERT INTO product_index_jobs(product_id,revision)
 SELECT product_id,search_revision FROM product WHERE category_id=NEW.category_id
 ON CONFLICT(product_id) DO UPDATE SET revision=excluded.revision,operation='upsert',status='pending',attempts=0,error=NULL,next_attempt_at=0,updated_at=datetime('now');
END;
