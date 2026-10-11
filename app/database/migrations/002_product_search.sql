ALTER TABLE product ADD COLUMN search_revision INTEGER NOT NULL DEFAULT 1;
CREATE VIRTUAL TABLE product_fts USING fts5(name, category, description, tokenize='unicode61');
CREATE TABLE product_index_jobs (
    product_id INTEGER PRIMARY KEY,
    revision INTEGER NOT NULL,
    operation TEXT NOT NULL DEFAULT 'upsert' CHECK(operation IN ('upsert','delete')),
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','failed','done')),
    attempts INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    next_attempt_at REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX product_index_jobs_pending ON product_index_jobs(status,next_attempt_at);
INSERT INTO product_fts(rowid,name,category,description)
 SELECT p.product_id,p.name,c.name,p.description FROM product p JOIN category c USING(category_id);
INSERT INTO product_index_jobs(product_id,revision) SELECT product_id,search_revision FROM product;

CREATE TRIGGER product_search_insert AFTER INSERT ON product BEGIN
 INSERT INTO product_fts(rowid,name,category,description)
 VALUES(NEW.product_id,NEW.name,(SELECT name FROM category WHERE category_id=NEW.category_id),NEW.description);
 INSERT INTO product_index_jobs(product_id,revision) VALUES(NEW.product_id,NEW.search_revision)
 ON CONFLICT(product_id) DO UPDATE SET revision=excluded.revision,operation='upsert',status='pending',attempts=0,error=NULL,next_attempt_at=0,updated_at=datetime('now');
END;

CREATE TRIGGER product_search_update AFTER UPDATE OF name,description,category_id,price,stock_quantity,image_path ON product
WHEN OLD.name IS NOT NEW.name OR OLD.description IS NOT NEW.description OR OLD.category_id IS NOT NEW.category_id
 OR OLD.price IS NOT NEW.price OR OLD.stock_quantity IS NOT NEW.stock_quantity OR OLD.image_path IS NOT NEW.image_path
BEGIN
 UPDATE product SET search_revision=OLD.search_revision+1 WHERE product_id=NEW.product_id;
 DELETE FROM product_fts WHERE rowid=NEW.product_id;
 INSERT INTO product_fts(rowid,name,category,description)
 VALUES(NEW.product_id,NEW.name,(SELECT name FROM category WHERE category_id=NEW.category_id),NEW.description);
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
 INSERT INTO product_fts(rowid,name,category,description)
 SELECT product_id,name,NEW.name,description FROM product WHERE category_id=NEW.category_id;
 INSERT INTO product_index_jobs(product_id,revision)
 SELECT product_id,search_revision FROM product WHERE category_id=NEW.category_id
 ON CONFLICT(product_id) DO UPDATE SET revision=excluded.revision,operation='upsert',status='pending',attempts=0,error=NULL,next_attempt_at=0,updated_at=datetime('now');
END;
